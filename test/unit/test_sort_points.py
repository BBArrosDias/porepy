import unittest
import numpy as np

from porepy.utils import sort_points


class SortLinePairTest(unittest.TestCase):
    def test_quad(self):
        p = np.array([[1, 2], [5, 1], [2, 7], [7, 5]]).T
        sp = sort_points.sort_point_pairs(p)
        # Use numpy arrays to ease comparison of points
        truth = np.array([[1, 2], [2, 7], [7, 5], [5, 1]]).T
        self.assertTrue(np.allclose(truth, sp))

class SortTriangleEdges(unittest.TestCase):

    def test_no_sorting(self):

        t = np.array([[0, 1, 2], [2, 1, 3]]).T
        sorted_t = sort_points.sort_triangle_edges(t)

        truth = t
        self.assertTrue(np.allclose(sorted_t, truth))

    def test_sort_one(self):

        t = np.array([[0, 1, 2], [1, 2, 3]]).T
        sorted_t = sort_points.sort_triangle_edges(t)

        truth = np.array([[0, 1, 2], [2, 1, 3]]).T
        self.assertTrue(np.allclose(sorted_t, truth))

    def test_sort_one_2(self):

        t = np.array([[1, 3, 0], [3, 2, 1]]).T
        sorted_t = sort_points.sort_triangle_edges(t)

        truth = np.array([[1, 3, 0], [1, 2, 3]]).T
        self.assertTrue(np.allclose(sorted_t, truth))

    def test_two_fracs_sort_second_not_third(self):
        # The first will lead the second to be sorted, which again remove the need to sort the third
        t = np.array([[0, 1, 2], [1, 2, 3], [2, 3, 4]]).T

        sorted_t = sort_points.sort_triangle_edges(t)

        truth = np.array([[0, 1, 2], [2, 1, 3], [2, 3, 4]]).T
        self.assertTrue(np.allclose(sorted_t, truth))

    def test_two_fracs_sort_second_then_third(self):
        # The first will lead the second to be sorted, which again remove the need to sort the third
        t = np.array([[0, 1, 2], [1, 2, 3], [3, 2, 4]]).T

        sorted_t = sort_points.sort_triangle_edges(t)

        truth = np.array([[0, 1, 2], [2, 1, 3], [2, 3, 4]]).T
        self.assertTrue(np.allclose(sorted_t, truth))

    def test_four_fracs_last_sorted_automatically(self):
        t = np.array([[0, 1, 2], [1, 2, 3], [3, 2, 4], [0, 4, 2]]).T
        sorted_t = sort_points.sort_triangle_edges(t)

        truth = np.array([[0, 1, 2], [2, 1, 3], [2, 3, 4], [2, 4, 0]]).T
        self.assertTrue(np.allclose(sorted_t, truth))


if __name__ == "__main__":
    unittest.main()
