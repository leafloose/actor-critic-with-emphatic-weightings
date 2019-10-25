import numpy as np


class LinearTDC:

    def __init__(self, num_features, alpha_v, alpha_w, lambda_c):
        self.alpha_v = alpha_v
        self.alpha_w = alpha_w
        self.lambda_c = lambda_c
        self.e = np.zeros(num_features)
        self.v = np.zeros(num_features)
        self.w = np.zeros(num_features)

    def learn(self, delta_t, x_t, gamma_t, x_tp1, gamma_tp1, rho_t):
        self.e = rho_t * (gamma_t * self.lambda_c * self.e + x_t)
        self.v += self.alpha_v * (delta_t * self.e - gamma_tp1 * (1 - self.lambda_c) * self.e.dot(self.w) * x_tp1)
        self.w += self.alpha_w * (delta_t * self.e - x_t.dot(self.w) * x_t)

    def estimate(self, x_t):
        return self.v.dot(x_t)


class BinaryTDC:

    def __init__(self, num_features, alpha_v, alpha_w, lambda_c):
        self.alpha_v = alpha_v
        self.alpha_w = alpha_w
        self.lambda_c = lambda_c
        self.e = np.zeros(num_features)
        self.v = np.zeros(num_features)
        self.w = np.zeros(num_features)

    def learn(self, delta_t, indices_t, gamma_t, indices_tp1, gamma_tp1, rho_t):
        self.e *= rho_t * gamma_t * self.lambda_c
        self.e[indices_t] += rho_t
        self.v += self.alpha_v * delta_t * self.e
        self.v[indices_tp1] -= self.alpha_v * gamma_tp1 * (1 - self.lambda_c) * self.e.dot(self.w)
        self.w[indices_t] -= self.alpha_w * self.w[indices_t].sum()
        self.w += self.alpha_w * delta_t * self.e

    def estimate(self, indices):
        return self.v[indices].sum()