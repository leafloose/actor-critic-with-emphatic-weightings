import numpy as np


# TODO: Implement action-value estimates instead of using TD error (which is higher variance due to the sampling of next states).
# TODO: Derive and implement eligibility traces for actor?


class ACE:

    def __init__(self, num_actions, num_features):
        self.theta = np.zeros((num_actions, num_features))
        self.F = 0.
        self.rho_tm1 = 1.
        self.psi_s_a = np.zeros((num_actions, num_features))
        self.psi_s_b = np.zeros((num_actions, num_features))

    def pi(self, indices):
        logits = self.theta[:, indices].sum(axis=1)
        # Converts potential overflows of the largest probability into underflows of the lowest probability:
        logits = logits - logits.max()
        exp_logits = np.exp(logits)
        return exp_logits / np.sum(exp_logits)

    def grad_log_pi(self, indices, a_t):
        self.psi_s_a.fill(0.)
        self.psi_s_a[a_t, indices] = 1.
        pi = np.expand_dims(self.pi(indices), axis=1)  # Add dimension to enable broadcasting.
        self.psi_s_b.fill(0.)
        self.psi_s_b[:, indices] = 1.
        return self.psi_s_a - pi * self.psi_s_b

    def learn(self, gamma_t, i_t, eta_t, alpha_t, rho_t, delta_t, indices_t, a_t):
        self.F = self.rho_tm1 * gamma_t * self.F + i_t
        M_t = (1 - eta_t) * i_t + eta_t * self.F
        self.theta += alpha_t * rho_t * M_t * delta_t * self.grad_log_pi(indices_t, a_t)
        self.rho_tm1 = rho_t