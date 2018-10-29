"""
Coupling conditions between subdomains for elliptic equations.

Current content:
    Robin-type couplings, as decsribed by Martin et al 2005.

Future content:
    Full continuity conditions between subdomains, to replace the old concept
    of 'DFN' discretizations
    @RUNAR: The periodic conditions you defined should also enter here, don't
    you think?

"""
import numpy as np
import scipy.sparse as sps

import porepy as pp
from porepy.numerics.mixed_dim.abstract_coupling import AbstractCoupling


class RobinCoupling(object):
    """ A condition with resistance to flow between subdomains. Implementation
        of the model studied (though not originally proposed) by Martin et
        al 2005.

        @ALL: We should probably make an abstract superclass for all couplers,
        similar to for all elliptic discretizations, so that new
        implementations know what must be done.

    """

    def __init__(self, keyword):
        self.keyword = keyword

    def _key(self):
        return self.keyword + '_'

    def _discretization_key(self):
        return self._key() + pp.keywords.DISCRETIZATION

    def ndof(self, mg):
        return mg.num_cells

    def discretize(self, g_h, g_l, data_h, data_l, data_edge):
        """ Discretize the interface law and store the discretization in the
        edge data.

        TODO: Right now, we are a bit unclear on whether it is required that g_h
        represents the higher-dimensional domain. It should not need to do so.
        TODO: Clean up in the aperture concept.

        Parameters:
            g_h: Grid of the master domanin.
            g_l: Grid of the slave domain.
            data_h: Data dictionary for the master domain.
            data_l: Data dictionary for the slave domain.
            data_edge: Data dictionary for the edge between the domains.

        """

        # Mortar data structure.
        mg = data_edge["mortar_grid"]

        faces_h, cells_h, sign_h = sps.find(g_h.cell_faces)
        ind_faces_h = np.unique(faces_h, return_index=True)[1]
        cells_h = cells_h[ind_faces_h]

        inv_M = sps.diags(1. / mg.cell_volumes)

        # Normal permeability and aperture of the intersection
        inv_k = 1. / (2. * data_edge["kn"])
        aperture_h = data_h["param"].get_aperture()

        proj = mg.master_to_mortar_avg()

        Eta = sps.diags(np.divide(inv_k, proj * aperture_h[cells_h]))

        # @ALESSIO, @EIRIK: the tpfa and vem couplers use different sign
        # conventions here. We should be very careful.
        data_edge[self._key() + 'Robin_discr'] = -inv_M * Eta


    def assemble_matrix_rhs(self, g_master, g_slave, data_master, data_slave, data_edge, matrix):
        """ Assemble the dicretization of the interface law, and its impact on
        the neighboring domains.

        Parameters:
            g_master: Grid on one neighboring subdomain.
            g_slave: Grid on the other neighboring subdomain.
            data_master: Data dictionary for the master suddomain
            data_slave: Data dictionary for the slave subdomain.
            data_edge: Data dictionary for the edge between the subdomains
            matrix_master: original discretization for the master subdomain
            matrix_slave: original discretization for the slave subdomain

            The discretization matrices must be included since they will be
            changed by the imposition of Neumann boundary conditions on the
            internal boundary in some numerical methods (Read: VEM, RT0)

        """
        if not self._key() + "Robin_discr" in data_edge.keys():
            self.discretize(g_master, g_slave, data_master, data_slave, data_edge)

        assert g_master.dim != g_slave.dim
        grid_swap = g_master.dim < g_slave.dim
        if grid_swap:
            g_master, g_slave = g_slave, g_master
            data_master, data_slave = data_slave, data_master

        # Generate matrix for the coupling. This can probably be generalized
        # once we have decided on a format for the general variables
        mg = data_edge["mortar_grid"]

        discr_master = data_master[self._discretization_key()]
        discr_slave = data_slave[self._discretization_key()]

        dof_master = discr_master.ndof(g_master)
        dof_slave = discr_slave.ndof(g_slave)

        # We know the number of dofs from the master and slave side from their
        # discretizations
        dof = np.array([dof_master, dof_slave, mg.num_cells])
        cc = np.array([sps.coo_matrix((i, j)) for i in dof for j in dof])
        cc = cc.reshape((3, 3))

        # The convention, for now, is to put the higher dimensional information
        # in the first column and row in matrix, lower-dimensional in the second
        # and mortar variables in the third
        cc[2, 2] = data_edge[self._key() + 'Robin_discr']

        discr_master.assemble_int_bound_pressure_trace(g_master, data_master, data_edge, grid_swap, cc, matrix, self_ind=0)
        discr_master.assemble_int_bound_flux(g_master, data_master, data_edge, grid_swap, cc, matrix, self_ind=0)

        discr_slave.assemble_int_bound_pressure_cell(g_slave, data_slave, data_edge, grid_swap, cc, matrix, self_ind=1)
        discr_slave.assemble_int_bound_source(g_slave, data_slave, data_edge, grid_swap, cc, matrix, self_ind=1)

        matrix += cc

        discr_master.enforce_neumann_int_bound(g_master, data_edge, matrix)
        # The rhs is just zeros
        rhs = np.array([np.zeros(dof_master), np.zeros(dof_slave), np.zeros(mg.num_cells)])
        return matrix, rhs


