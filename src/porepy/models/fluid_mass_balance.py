"""
Class types:
    MassBalanceEquations defines subdomain and interface equations through the
        terms entering. Darcy type interface relation is assumed.
    Specific ConstitutiveEquations and specific SolutionStrategy for both incompressible
    and compressible case.

Notes:
    Apertures and specific volumes are not included.

    Refactoring needed for constitutive equations. Modularisation and moving to the
    library.

    Upwind for the mobility of the fluid flux is not complete.

"""

from __future__ import annotations

import logging
from numbers import Number
from typing import Dict, Optional

import numpy as np

import porepy as pp

from .constitutive_laws import ad_wrapper

logger = logging.getLogger(__name__)


class MassBalanceEquations(pp.ScalarBalanceEquation):
    """Mixed-dimensional mass balance equation.

    Balance equation for all subdomains and Darcy-type flux relation on all interfaces
    of codimension one.

    FIXME: Well equations? Low priority.

    """

    def set_equations(self):
        """Set the equations for the mass balance problem.

        A mass balance equation is set for all subdomains and a Darcy-type flux relation
        is set for all interfaces of codimension one.
        """
        subdomains = self.mdg.subdomains()
        interfaces = self.mdg.interfaces()
        sd_eq = self.mass_balance_equation(subdomains)
        intf_eq = self.interface_darcy_flux_equation(interfaces)
        self.equation_system.set_equation(sd_eq, subdomains, {"cells": 1})
        self.equation_system.set_equation(intf_eq, interfaces, {"cells": 1})

    def mass_balance_equation(self, subdomains: list[pp.Grid]) -> pp.ad.Operator:
        """Mass balance equation for subdomains.

        Parameters:
            subdomains: List of subdomains.

        Returns:
            Operator representing the mass balance equation.

        """
        accumulation = self.fluid_mass(subdomains)
        flux = self.fluid_flux(subdomains)
        source = self.fluid_source(subdomains)
        eq = self.balance_equation(subdomains, accumulation, flux, source)
        eq.set_name("mass_balance_equation")
        return eq

    def fluid_mass(self, subdomains: list[pp.Grid]) -> pp.ad.Operator:
        """Fluid mass.

        This implementation assumes constant porosity and must be overridden for
        variable porosity. This has to do with wrapping of scalars as vectors or
        matrices and will hopefully be improved in the future. Extension to variable
        density is straightforward.

        Parameters:
            subdomains: List of subdomains.

        Returns:
            Operator representing the fluid mass.
        """

        mass_density = self.fluid_density(subdomains) * self.porosity(subdomains)
        mass = self.volume_integral(mass_density, subdomains)
        mass.set_name("fluid_mass")
        return mass

    def fluid_flux(self, subdomains: list[pp.Grid]) -> pp.ad.Operator:
        """Fluid flux.

        Darcy flux times density and mobility.

        Parameters:
            subdomains: List of subdomains.

        Returns:
            Operator representing the fluid flux.
        """
        discr = self.mobility_discretization(subdomains)
        mob_rho = self.fluid_density(subdomains) * self.mobility(subdomains)

        bc_values = self.bc_values_mobrho(subdomains)
        flux = self.advective_flux(
            subdomains, mob_rho, discr, bc_values, self.interface_fluid_flux
        )
        flux.set_name("fluid_flux")
        return flux

    def interface_flux_equation(
        self, interfaces: list[pp.MortarGrid]
    ) -> pp.ad.Operator:
        """Interface flux equation.

        Parameters:
            interfaces: List of interface grids.

        Returns:
            Operator representing the interface flux equation.

        """
        return self.interface_darcy_flux_equation(interfaces)

    def interface_fluid_flux(self, interfaces: list[pp.MortarGrid]) -> pp.ad.Operator:
        """Interface fluid flux.

        Parameters:
            interfaces: List of interface grids.

        Returns:
            Operator representing the interface fluid flux.

        """
        subdomains = self.interfaces_to_subdomains(interfaces)
        discr = self.interface_mobility_discretization(interfaces)
        mob_rho = self.mobility(subdomains) * self.fluid_density(subdomains)
        # Call to constitutive law for advective fluxes.
        flux: pp.ad.Operator = self.interface_advective_flux(interfaces, mob_rho, discr)
        flux.set_name("interface_fluid_flux")
        return flux

    def fluid_source(self, subdomains: list[pp.Grid]) -> pp.ad.Operator:
        """Fluid source term.

        Parameters:
            subdomains: List of subdomains.

        Returns:
            Operator representing the source term.

        """
        num_cells = sum([sd.num_cells for sd in subdomains])
        vals = np.zeros(num_cells)
        source = pp.ad.Array(vals, "fluid_source")
        return source


class ConstitutiveEquationsIncompressibleFlow(
    pp.constitutive_laws.DarcysLawFV,
    pp.constitutive_laws.DimensionReduction,
    pp.constitutive_laws.AdvectiveFlux,
    pp.constitutive_laws.ConstantPorousMedium,
    pp.constitutive_laws.ConstantSinglePhaseFluid,
):
    """Constitutive equations for incompressible flow."""

    def mobility(self, subdomains: list[pp.Grid]) -> pp.ad.Operator:
        """Mobility of the fluid flux.

        Parameters:
            subdomains: List of subdomains.

        Returns:
            Operator representing the mobility.
        """
        return pp.ad.Scalar(1) / self.fluid_viscosity(subdomains)

    def mobility_discretization(
        self, subdomains: list[pp.Grid]
    ) -> pp.ad.Discretization:
        return pp.ad.UpwindAd(self.mobility_discretization_parameter_key, subdomains)

    def interface_mobility_discretization(
        self, interfaces: list[pp.MortarGrid]
    ) -> pp.ad.Discretization:
        """

        Parameters:
            interfaces: List of interface grids.

        Returns:
            Discretization for the interface mobility.

        """
        return pp.ad.UpwindCouplingAd(
            self.mobility_discretization_parameter_key, interfaces
        )

    def bc_values_darcy_flux(self, subdomains: list[pp.Grid]) -> pp.ad.Array:
        """
        Not sure where this one should reside. Note that we could remove the
        grid_operator BC and DirBC, probably also ParameterArray/Matrix (unless needed
        to get rid of pp.ad.Discretization. I don't see how it would be, though).
        Parameters:
            subdomains:

        Returns:

        """
        num_faces = sum([sd.num_faces for sd in subdomains])
        return ad_wrapper(0, True, num_faces, "bc_values_darcy")

    def bc_values_mobrho(self, subdomains: list[pp.Grid]) -> pp.ad.Array:
        """

        Units for Dirichlet: kg * m^-3 * Pa^-1 * s^-1 ..note:
            Value is tricky if ..math:
                mobility = \\rho / \\mu
            with \rho and \mu being functions of p (or other variables), since variables
            are not defined at the boundary. This may lead to inconsistency between
            boundary conditions for Darcy flux and mobility. For now, we assume that the
            mobility is constant. TODO: Better solution. Could involve defining boundary
            grids.
        Parameters:
            subdomains: List of subdomains.

        Returns:
            Array with boundary values for the mobility.

        """
        # List for all subdomains
        bc_values = []

        # Loop over subdomains to collect boundary values
        for sd in subdomains:
            rho_by_mu = (
                self.fluid_density([sd]) / self.fluid_viscosity([sd])
            ).evaluate(self.equation_system)
            # Unlike Operators, wrapped constants (Scalar, Array) do not have val
            # attribute.
            if hasattr(rho_by_mu, "val"):
                rho_by_mu = rho_by_mu.val

            vals = np.zeros(sd.num_faces)
            all_bf, *_ = self.domain_boundary_sides(sd)
            if isinstance(rho_by_mu, Number):
                # Scalar value, simple assignment
                vals[all_bf] = rho_by_mu
            else:
                # Array value, assumed to be cell-wise
                assert isinstance(rho_by_mu, np.ndarray)
                assert rho_by_mu.shape == (sd.num_cells,)
                trace = np.abs(sd.cell_faces)
                vals[all_bf] = (trace * rho_by_mu)[all_bf]
            # Append to list of boundary values
            bc_values.append(vals)

        # Concatenate to single array and wrap as ad.Array
        bc_values = ad_wrapper(np.hstack(bc_values), True, name="bc_values_mobility")
        return bc_values


class ConstitutiveEquationsCompressibleFlow(
    pp.constitutive_laws.FluidDensityFromPressure,
    ConstitutiveEquationsIncompressibleFlow,
):
    """Resolution order is important:
    Left to right, i.e., DensityFromPressure mixin's method is used when calling
    self.fluid_density
    """

    pass


class VariablesSinglePhaseFlow:
    """
    Creates necessary variables (pressure, interface flux) and provides getter methods
    for these and their reference values. Getters construct mixed-dimensional variables
    on the fly, and can be called on any subset of the grids where the variable is
    defined. Setter method (assig_variables), however, must create on all grids where
    the variable is to be used.

    .. note::
        Wrapping in class methods and not calling equation_system directly allows for easier
        changes of primary variables. As long as all calls to fluid_flux() accept Operators as
        return values, we can in theory add it as a primary variable and solved mixed form.
        Similarly for different formulations of the pressure (e.g. pressure head) or enthalpy/
        temperature for the energy equation.
    """

    def create_variables(self) -> None:
        """
        Assign primary variables to subdomains and interfaces of the mixed-dimensional
        grid. Old implementation awaiting SystemManager

        """
        self.equation_system.create_variables(
            self.pressure_variable,
            subdomains=self.mdg.subdomains(),
        )
        self.equation_system.create_variables(
            self.interface_darcy_flux_variable,
            interfaces=self.mdg.interfaces(),
        )

    def pressure(self, subdomains) -> pp.ad.MixedDimensionalVariable:
        p = self.equation_system.md_variable(self.pressure_variable, subdomains)
        return p

    def interface_darcy_flux(
        self, interfaces: list[pp.MortarGrid]
    ) -> pp.ad.MixedDimensionalVariable:
        """Interface Darcy flux.

        Parameters:
            interfaces: List of interface grids.

        Returns:
            Variable representing the interface Darcy flux.
        """
        flux = self.equation_system.md_variable(
            self.interface_darcy_flux_variable, interfaces
        )
        return flux

    def reference_pressure(self, subdomains: list[pp.Grid]) -> pp.ad.Operator:
        """Reference pressure.

        Parameters:
            subdomains: List of subdomains.

            Returns:
                Operator representing the reference pressure.

        TODO: Confirm that this is the right place for this method. # IS: Definitely not
        a Material. Most closely related to the constitutive laws. # Perhaps create a
        reference values class that is a mixin to the constitutive laws? # Could have
        values in the init and methods returning operators just as # this method.
        """
        p_ref = self.fluid.convert_units(0, "Pa")
        size = sum([sd.num_cells for sd in subdomains])
        return ad_wrapper(p_ref, True, size, name="reference_pressure")


class SolutionStrategyIncompressibleFlow(pp.SolutionStrategy):
    """This is whatever is left of pp.IncompressibleFlow.

    At some point, this will be refined to be a more sophisticated (modularised)
    solution strategy class. More refactoring may be beneficial.

    This is *not* a full-scale model (in the old sense), but must be mixed with balance
    equations, constitutive laws etc. See user_examples.

    """

    def __init__(self, params: Optional[Dict] = None) -> None:
        super().__init__(params)
        # Variables
        self.pressure_variable: str = "pressure"
        self.interface_darcy_flux_variable: str = "interface_darcy_flux"
        self.darcy_discretization_parameter_key: str = "flow"
        self.mobility_discretization_parameter_key: str = "mobility"

    def initial_condition(self) -> None:
        """New formulation requires darcy flux (the flux is "advective" with mobilities
        included).

        """
        super().initial_condition()
        for sd, data in self.mdg.subdomains(return_data=True):
            pp.initialize_data(
                sd,
                data,
                self.mobility_discretization_parameter_key,
                {"darcy_flux": np.zeros(sd.num_faces)},
            )
        for intf, data in self.mdg.interfaces(return_data=True):
            pp.initialize_data(
                intf,
                data,
                self.mobility_discretization_parameter_key,
                {"darcy_flux": np.zeros(intf.num_cells)},
            )

    def set_discretization_parameters(self) -> None:
        """Set default (unitary/zero) parameters for the flow problem.

        The parameter fields of the data dictionaries are updated for all subdomains and
        interfaces (of codimension 1).
        """
        for sd, data in self.mdg.subdomains(return_data=True):

            specific_volume_mat = self.specific_volume([sd]).evaluate(
                self.equation_system
            )
            # Extract diagonal of the specific volume matrix.
            specific_volume = specific_volume_mat * np.ones(sd.num_cells)
            # Check that the matrix is actually diagonal.
            assert np.all(np.isclose(specific_volume, specific_volume_mat.data))

            kappa = self.permeability([sd])
            diffusivity = pp.SecondOrderTensor(kappa * specific_volume)

            pp.initialize_data(
                sd,
                data,
                self.darcy_discretization_parameter_key,
                {
                    "bc": self.bc_type_darcy(sd),
                    "second_order_tensor": diffusivity,
                    "ambient_dimension": self.nd,
                },
            )
            pp.initialize_data(
                sd,
                data,
                self.mobility_discretization_parameter_key,
                {
                    "bc": self.bc_type_mobrho(sd),
                    "second_order_tensor": diffusivity,
                    "ambient_dimension": self.nd,
                },
            )

        # Assign diffusivity in the normal direction of the fractures.
        for intf, intf_data in self.mdg.interfaces(return_data=True):
            pp.initialize_data(
                intf,
                intf_data,
                self.darcy_discretization_parameter_key,
                {
                    "ambient_dimension": self.nd,
                },
            )

    def bc_type_darcy(self, sd: pp.Grid) -> pp.BoundaryCondition:
        """Dirichlet conditions on all external boundaries.

        Parameters:
            sd: Subdomain grid on which to define boundary conditions.

        Returns:
            Boundary condition object.
        """
        # Define boundary regions
        all_bf, *_ = self.domain_boundary_sides(sd)
        # Define boundary condition on faces
        return pp.BoundaryCondition(sd, all_bf, "dir")

    def bc_type_mobrho(self, sd: pp.Grid) -> pp.BoundaryCondition:
        """Dirichlet conditions on all external boundaries.

        Parameters:
            sd: Subdomain grid on which to define boundary conditions.

        Returns:
            Boundary condition object.
        """
        # Define boundary regions
        all_bf, *_ = self.domain_boundary_sides(sd)
        # Define boundary condition on faces
        return pp.BoundaryCondition(sd, all_bf, "dir")

    def before_nonlinear_iteration(self):
        """
        Evaluate Darcy flux for each subdomain and interface and store in the data
        dictionary for use in upstream weighting.

        """
        for sd, data in self.mdg.subdomains(return_data=True):
            vals = self.darcy_flux([sd]).evaluate(self.equation_system).val
            data[pp.PARAMETERS][self.mobility_discretization_parameter_key].update(
                {"darcy_flux": vals}
            )

        for intf, data in self.mdg.interfaces(return_data=True):
            vals = self.interface_darcy_flux([intf]).evaluate(self.equation_system).val
            data[pp.PARAMETERS][self.mobility_discretization_parameter_key].update(
                {"darcy_flux": vals}
            )
        # FIXME: Rediscretize upwind.


"""
Compressible flow below.

Note on time dependency: I'm tempted to suggest assigning time_manager to stationary
models and partially remove the distinction with transient ones.
"""


class SolutionStrategyCompressibleFlow(SolutionStrategyIncompressibleFlow):
    """This class extends the Incompressible flow model by including a
    cumulative term expressed through pressure and a constant compressibility
    coefficient. For a full documentation refer to the parent class.

    The simulation starts at time t=0.



    Attributes:
        time_manager: Time-stepping control manager.

    """

    def __init__(self, params: Optional[Dict] = None) -> None:
        """
        Parameters:
            params (dict): Dictionary of parameters used to control the solution
            procedure.
                Some frequently used entries are file and folder names for export, mesh
                sizes...
        """
        if params is None:
            params = {}
        super().__init__(params)

        # Time manager
        self.time_manager = params.get(
            "time_manager",
            pp.TimeManager(schedule=[0, 1], dt_init=1, constant_dt=True),
        )

    def _export(self):
        if hasattr(self, "exporter"):
            self.exporter.write_vtu([self.variable], time_dependent=True)

    def after_simulation(self):
        self.exporter.write_pvd()
