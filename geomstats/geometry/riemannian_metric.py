"""Riemannian and pseudo-Riemannian metrics."""

import autograd

import geomstats.backend as gs
import geomstats.vectorization
from geomstats.geometry.connection import Connection
from geomstats.integrator import integrate

EPSILON = 1e-4
N_CENTERS = 10
TOLERANCE = 1e-5
N_REPETITIONS = 20
N_MAX_ITERATIONS = 50000
N_STEPS = 10


def loss(y_pred, y_true, metric):
    """Compute loss function between prediction and ground truth.

    Loss function given by a Riemannian metric,
    expressed as the squared geodesic distance between the prediction
    and the ground truth.

    Parameters
    ----------
    y_pred : array-like, shape=[..., dim]
        Prediction.
    y_true : array-like, shape=[..., dim]
        Ground-truth.
    metric : RiemannianMetric
        Metric.

    Returns
    -------
    sq_dist : array-like, shape=[...,]
        Loss, i.e. the squared distance.
    """
    sq_dist = metric.squared_dist(y_pred, y_true)
    return sq_dist


def grad(y_pred, y_true, metric):
    """Closed-form for the gradient of the loss function.

    Parameters
    ----------
    y_pred : array-like, shape=[..., dim]
        Prediction.
    y_true : array-like, shape=[..., dim]
        Ground-truth.
    metric : RiemannianMetric
        Metric.

    Returns
    -------
    loss_grad : array-like, shape=[...,]
        Gradient of the loss.

    """
    tangent_vec = metric.log(base_point=y_pred, point=y_true)
    grad_vec = - 2. * tangent_vec

    inner_prod_mat = metric.metric_matrix(base_point=y_pred)
    is_vectorized = inner_prod_mat.ndim == 3
    axes = (0, 2, 1) if is_vectorized else (1, 0)

    loss_grad = gs.einsum(
        '...i,...ij->...i',
        grad_vec,
        gs.transpose(inner_prod_mat, axes=axes))

    return loss_grad


class RiemannianMetric(Connection):
    """Class for Riemannian and pseudo-Riemannian metrics.

    The associated connection is the Levi-Civita connection on the tangent space.

    Parameters
    ----------
    dim : int
        Dimension of the manifold.
    signature : tuple
        Signature of the metric.
        Optional, default: None.
    default_point_type : str, {'vector', 'matrix'}
        Point type.
        Optional, default: 'vector'.
    """

    def __init__(self, dim, signature=None, default_point_type='vector'):
        super(RiemannianMetric, self).__init__(
            dim=dim, default_point_type=default_point_type)
        self.signature = signature

    def metric_matrix(self, base_point=None):
        """Metric matrix at the tangent space at a base point.

        Parameters
        ----------
        base_point : array-like, shape=[..., dim]
            Base point.
            Optional, default: None.

        Returns
        -------
        mat : array-like, shape=[..., dim, dim]
            Inner-product matrix.
        """
        raise NotImplementedError(
            'The computation of the metric matrix'
            ' is not implemented.')

    def inner_product_inverse_matrix(self, base_point=None):
        """Inner product matrix at the tangent space at a base point.

        Parameters
        ----------
        base_point : array-like, shape=[..., dim]
            Base point.
            Optional, default: None.

        Returns
        -------
        mat : array-like, shape=[..., dim, dim]
            Inverse of inner-product matrix.
        """
        metric_matrix = self.metric_matrix(base_point)
        cometric_matrix = gs.linalg.inv(metric_matrix)
        return cometric_matrix

    def inner_product_derivative_matrix(self, base_point=None):
        """Compute derivative of the inner prod matrix at base point.

        Parameters
        ----------
        base_point : array-like, shape=[..., dim]
            Base point.
            Optional, default: None.

        Returns
        -------
        mat : array-like, shape=[..., dim, dim]
            Derivative of inverse of inner-product matrix.
        """
        metric_derivative = autograd.jacobian(self.metric_matrix)
        return metric_derivative(base_point)

    def christoffels(self, base_point):
        """Compute Christoffel symbols associated with the connection.

        Parameters
        ----------
        base_point: array-like, shape=[..., dim]
            Base point.

        Returns
        -------
        christoffels: array-like, shape=[..., dim, dim, dim]
            Christoffel symbols.
        """
        cometric_mat_at_point = self.inner_product_inverse_matrix(base_point)
        metric_derivative_at_point = self.inner_product_derivative_matrix(
            base_point)
        term_1 = gs.einsum('...im,...mkl->...ikl',
                           cometric_mat_at_point,
                           metric_derivative_at_point)
        term_2 = gs.einsum('...im,...mlk->...ilk',
                           cometric_mat_at_point,
                           metric_derivative_at_point)
        term_3 = - gs.einsum('...im,...klm->...ikl',
                             cometric_mat_at_point,
                             metric_derivative_at_point)

        christoffels = 0.5 * (term_1 + term_2 + term_3)
        return christoffels

    @geomstats.vectorization.decorator(['else', 'vector', 'vector', 'vector'])
    def inner_product(self, tangent_vec_a, tangent_vec_b, base_point=None):
        """Inner product between two tangent vectors at a base point.

        Parameters
        ----------
        tangent_vec_a: array-like, shape=[..., dim]
            Tangent vector at base point.
        tangent_vec_b: array-like, shape=[..., dim]
            Tangent vector at base point.
        base_point: array-like, shape=[..., dim]
            Base point.
            Optional, default: None.

        Returns
        -------
        inner_product : array-like, shape=[...,]
            Inner-product.
        """
        inner_prod_mat = self.metric_matrix(base_point)
        inner_prod_mat = gs.to_ndarray(inner_prod_mat, to_ndim=3)

        aux = gs.einsum('...j,...jk->...k', tangent_vec_a, inner_prod_mat)

        inner_prod = gs.einsum('...k,...k->...', aux, tangent_vec_b)
        inner_prod = gs.to_ndarray(inner_prod, to_ndim=1)
        inner_prod = gs.to_ndarray(inner_prod, to_ndim=2, axis=1)

        return inner_prod

    def squared_norm(self, vector, base_point=None):
        """Compute the square of the norm of a vector.

        Squared norm of a vector associated to the inner product
        at the tangent space at a base point.

        Parameters
        ----------
        vector : array-like, shape=[..., dim]
            Vector.
        base_point : array-like, shape=[..., dim]
            Base point.
            Optional, default: None.

        Returns
        -------
        sq_norm : array-like, shape=[...,]
            Squared norm.
        """
        sq_norm = self.inner_product(vector, vector, base_point)
        return sq_norm

    def norm(self, vector, base_point=None):
        """Compute norm of a vector.

        Norm of a vector associated to the inner product
        at the tangent space at a base point.

        Note: This only works for positive-definite
        Riemannian metrics and inner products.

        Parameters
        ----------
        vector : array-like, shape=[..., dim]
            Vector.
        base_point : array-like, shape=[..., dim]
            Base point.
            Optional, default: None.

        Returns
        -------
        norm : array-like, shape=[...,]
            Norm.
        """
        sq_norm = self.squared_norm(vector, base_point)
        norm = gs.sqrt(sq_norm)
        return norm

    def squared_dist(self, point_a, point_b):
        """Squared geodesic distance between two points.

        Parameters
        ----------
        point_a : array-like, shape=[..., dim]
            Point.
        point_b : array-like, shape=[..., dim]
            Point.

        Returns
        -------
        sq_dist : array-like, shape=[...,]
            Squared distance.
        """
        log = self.log(point=point_b, base_point=point_a)

        sq_dist = self.squared_norm(vector=log, base_point=point_a)
        return sq_dist

    def dist(self, point_a, point_b):
        """Geodesic distance between two points.

        Note: It only works for positive definite
        Riemannian metrics.

        Parameters
        ----------
        point_a : array-like, shape=[..., dim]
            Point.
        point_b : array-like, shape=[..., dim]
            Point.

        Returns
        -------
        dist : array-like, shape=[...,]
            Distance.
        """
        sq_dist = self.squared_dist(point_a, point_b)
        dist = gs.sqrt(sq_dist)
        return dist

    def dist_pairwise(self, point):
        """Compute the pairwise distance between points.

        Parameters
        ----------
        point : array-like, shape=[n_samples, dim]
            Set of points in hyperbolic space.

        Returns
        -------
        dist : array-like, shape=[n_samples, n_samples]
            Pairwise distance matrix between all points.
        """
        pairwise_dist = []

        for i, x in enumerate(point):
            for y in point[i:]:
                pairwise_dist.append(self.dist(x, y))

        pairwise_dist = geomstats.geometry.symmetric_matrices.\
            SymmetricMatrices.from_vector(gs.array(pairwise_dist))

        return pairwise_dist

    def diameter(self, points):
        """Give the distance between two farthest points.

        Distance between the two points that are farthest away from each other
        in points.

        Parameters
        ----------
        points : array-like, shape=[..., dim]
            Points.

        Returns
        -------
        diameter : float
            Distance between two farthest points.
        """
        diameter = 0.0
        n_points = points.shape[0]

        for i in range(n_points - 1):
            dist_to_neighbors = self.dist(points[i, :], points[i + 1:, :])
            dist_to_farthest_neighbor = gs.amax(dist_to_neighbors)
            diameter = gs.maximum(diameter, dist_to_farthest_neighbor)

        return diameter

    def closest_neighbor_index(self, point, neighbors):
        """Closest neighbor of point among neighbors.

        Parameters
        ----------
        point : array-like, shape=[..., dim]
            Point.
        neighbors : array-like, shape=[..., dim]
            Neighbors.

        Returns
        -------
        closest_neighbor_index : int
            Index of closest neighbor.
        """
        dist = self.dist(point, neighbors)
        closest_neighbor_index = gs.argmin(dist)

        return closest_neighbor_index

    def orthonormal_basis(self, basis, base_point=None):
        """Orthonormalize the basis with respect to the metric.

        This corresponds to a renormalization.

        Parameters
        ----------
        basis : array-like, shape=[dim, dim]
            Matrix of a metric.
        base_point

        Returns
        -------
        basis : array-like, shape=[dim, n, n]
            Orthonormal basis.
        """
        norms = self.squared_norm(basis, base_point)

        return gs.einsum('i, ikl->ikl', 1. / gs.sqrt(norms), basis)


class RiemannianCometric(RiemannianMetric):
    """Class for Riemannian and pseudo-Riemannian cometrics.
    The associated connection is the Hamiltonian connection on the cotangent space.

    Parameters
    ----------
    dim : int
        Dimension of the manifold.
    signature : tuple
        Signature of the metric.
        Optional, default: None.
    default_point_type : str, {'vector', 'matrix'}
        Point type.
        Optional, default: 'vector'.
    """

    def __init__(self, dim, signature=None, default_point_type='vector'):
        super(RiemannianCometric, self).__init__(
            dim=dim, default_point_type=default_point_type)
        self.signature = signature

    def metric_matrix(self, base_point=None):
        """Metric matrix at the tangent space at a base point.

        Parameters
        ----------
        base_point : array-like, shape=[..., dim]
            Base point.
            Optional, default: None.

        Returns
        -------
        mat : array-like, shape=[..., dim, dim]
            Inner-product matrix.
        """
        cometric_matrix = self.cometric_matrix(base_point)
        metric_matrix = gs.linalg.inv(cometric_matrix)
        return metric_matrix

    def cometric_matrix(self, base_point=None):
        """Cometric matrix at the cotangent space at a base point.

        Parameters
        ----------
        base_point : array-like, shape=[..., dim]
            Base point.
            Optional, default: None.

        Returns
        -------
        mat : array-like, shape=[..., dim, dim]
            Inverse of inner-product matrix.
        """
        raise NotImplementedError(
            'The computation of the cometric matrix'
            ' is not implemented.')

    def inner_coproduct(self, covector_1, covector_2, base_point):
        r"""Computes the inner coproduct between two covectors at the base point.

        This is the inner product associated to the kernel matrix:
        .. math:

                <m, m'> = \sum_{i=1}^k m_i^T k(x_i, x_j) m_j

        Parameters
        ----------
        covector_1 : covector at `base_point`
        covector_2 : covector at `base_point`
        base_point : landmark configuration

        Returns
        -------
        inner_coproduct : float
        """

        vector_2 = gs.einsum(
            '...ij,...j->...i', self.cometric_matrix(base_point), covector_2)
        inner_coproduct = gs.einsum(
            '...i,...i->...', covector_1, vector_2)
        return inner_coproduct

    def hamiltonian(self, state):
        position, momentum = state
        return 1/2 * self.inner_coproduct(
            momentum, momentum, position)

    def Hamiltonian_equation(self, position, momentum):
        state = position, momentum
        H_q, H_p = gs.autograd.value_and_grad(self.hamiltonian)(state)
        return H_p, - H_q

    def exp(self, cotangent_vec, base_point, n_steps=N_STEPS, step='euler',
            point_type=None, **kwargs):
        """Exponential map associated to the affine connection on the cotangent bundle.

        Exponential map at base_point of cotangent_vec computed by integration
        of the geodesic equation (initial value problem), using the
        Hamiltonian equation

        Parameters
        ----------
        cotangent_vec : array-like, shape=[..., dim]
            Cotangent vector at the base point.
        base_point : array-like, shape=[..., dim]
            Point on the manifold.
        n_steps : int
            Number of discrete time steps to take in the integration.
            Optional, default: N_STEPS.
        step : str, {'euler', 'rk4'}
            The numerical scheme to use for integration.
            Optional, default: 'euler'.
        point_type : str, {'vector', 'matrix'}
            Type of representation used for points.
            Optional, default: None.

        Returns
        -------
        exp : array-like, shape=[..., dim]
            Point on the manifold.
        """

        initial_state = (base_point, cotangent_vec)
        flow, _ = integrate(self.Hamiltonian_equation, initial_state,
                            n_steps=n_steps, step=step)

        exp = flow[-1]
        return exp
