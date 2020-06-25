import unittest
import gym
import numpy as np
from tqdm import tqdm
import scipy.stats as st
import matplotlib.pyplot as plt
from joblib import Parallel, delayed
from src.algorithms.ace import BinaryACE
from src.algorithms.fhat import BinaryFHat
from src.algorithms.totd import BinaryTOTD
from src.algorithms.tdc import BinaryTDC
from src.function_approximation.tile_coder import TileCoder
from evaluate_policies import evaluate_policy


class ACETests(unittest.TestCase):

    def test_binary_ace_on_policy(self):
        env = gym.make('MountainCar-v0').unwrapped  # Get the underlying environment object to bypass the built-in timestep limit.
        env.seed(992390476)  # Seed generated by: np.random.randint(2**31 - 1)
        rng = env.np_random
        gamma = 1.
        tc = TileCoder(np.array([env.observation_space.low, env.observation_space.high]).T, [5, 5], 8, True)
        actor = BinaryACE(env.action_space.n, tc.total_num_tiles)
        critic = BinaryTOTD(tc.total_num_tiles, .1/tc.num_active_features, .9)
        indices_t = tc.encode(env.reset())
        gamma_t = 0.
        f_t = 0.
        for t in tqdm(range(2500)):
            a_t = rng.choice(env.action_space.n, p=actor.pi(indices_t))  # Select action.
            s_tp1, r_tp1, terminal, _ = env.step(a_t)  # Interact with environment.
            if terminal:
                gamma_tp1 = 0.
                s_tp1 = env.reset()
            else:
                gamma_tp1 = gamma
            indices_tp1 = tc.encode(s_tp1)
            v_t = critic.estimate(indices_t)
            v_tp1 = critic.estimate(indices_tp1)
            delta_t = r_tp1 + gamma_tp1 * v_tp1 - v_t  # Compute TD error.
            critic.learn(delta_t, v_t, indices_t, gamma_t, v_tp1)  # Update critic.
            f_t = 1 * gamma_t * f_t + 0
            actor.learn(1., 1 if gamma_t == 0. else 0., .01, 1., delta_t, indices_t, a_t, f_t)  # Update actor.
            indices_t = indices_tp1
            gamma_t = gamma_tp1
        env.reset()
        g_t = evaluate_policy(actor, tc, env, rng=rng)
        self.assertGreater(g_t, -200)

    def test_low_variance_binary_ace_on_policy(self):
        env = gym.make('MountainCar-v0').unwrapped  # Get the underlying environment object to bypass the built-in timestep limit.
        env.seed(947366491)  # Seed generated by: np.random.randint(2**31 - 1)
        gamma = 1.
        tc = TileCoder(np.array([env.observation_space.low, env.observation_space.high]).T, [5, 5], 8, True)
        fhat = BinaryFHat(tc.total_num_tiles, .01)
        actor = BinaryACE(env.action_space.n, tc.total_num_tiles)
        critic = BinaryTOTD(tc.total_num_tiles, .1/tc.num_active_features, .9)
        indices_t = tc.encode(env.reset())
        gamma_t = 0.
        for t in tqdm(range(2500)):
            a_t = np.random.choice(env.action_space.n, p=actor.pi(indices_t))  # Select action.
            s_tp1, r_tp1, terminal, _ = env.step(a_t)  # Interact with environment.
            if terminal:
                gamma_tp1 = 0.
                s_tp1 = env.reset()
            else:
                gamma_tp1 = gamma
            indices_tp1 = tc.encode(s_tp1)
            v_t = critic.estimate(indices_t)
            v_tp1 = critic.estimate(indices_tp1)
            delta_t = r_tp1 + gamma_tp1 * v_tp1 - v_t  # Compute TD error.
            F_t = fhat.estimate(indices_t)
            critic.learn(delta_t, v_t, indices_t, gamma_t, v_tp1)  # Update critic.
            actor.learn(1., 1 if gamma_t == 0. else 0., .01, 1., delta_t, indices_t, a_t, F_t)  # Update actor.
            fhat.learn(indices_tp1, gamma_tp1, indices_t, rho_tm1=1., i_t=1.)
            indices_t = indices_tp1
            gamma_t = gamma_tp1
        env.reset()
        g_t = evaluate_policy(actor, tc, env)
        self.assertGreater(g_t, -200)

    def test_binary_ace_off_policy(self):
        num_runs = 2
        num_timesteps = 5000
        evaluation_interval = 1000
        num_evaluation_runs = 1
        rewards = np.zeros((num_runs, num_timesteps // evaluation_interval + 1, num_evaluation_runs))
        alpha_a = .001
        alpha_c = .05
        alpha_w = .0001
        lambda_c = 0.
        eta = 0.
        env = gym.make('MountainCar-v0').unwrapped
        env.seed(1202670738)
        rng = env.np_random
        tc = TileCoder(np.array([env.observation_space.low, env.observation_space.high]).T, [5, 5], 8, True)
        for run_num in range(num_runs):
            actor = BinaryACE(env.action_space.n, tc.total_num_tiles)
            critic = BinaryTDC(tc.total_num_tiles, alpha_c, alpha_w, lambda_c)
            indices_t = tc.encode(env.reset())
            gamma_t = 0.
            f_t = 0.
            rho_tm1 = 1.
            for t in tqdm(range(num_timesteps)):
                if t % evaluation_interval == 0:
                    rewards[run_num, t // evaluation_interval] = Parallel(n_jobs=-1)(delayed(evaluate_policy)(actor, tc, num_timesteps=1000) for _ in range(num_evaluation_runs))
                a_t = rng.choice(env.action_space.n)
                s_tp1, r_tp1, terminal, _ = env.step(a_t)
                if terminal:
                    s_tp1 = env.reset()
                    gamma_tp1 = 0.
                else:
                    gamma_tp1 = 1.
                indices_tp1 = tc.encode(s_tp1)
                pi_t = actor.pi(indices_t)
                mu_t = np.ones(env.action_space.n) / env.action_space.n
                rho_t = pi_t[a_t] / mu_t[a_t]
                delta_t = r_tp1 + gamma_tp1 * critic.estimate(indices_tp1) - critic.estimate(indices_t)
                critic.learn(delta_t, indices_t, gamma_t, indices_tp1, gamma_tp1, rho_t)
                f_t = rho_tm1 * gamma_t * f_t + 1
                actor.learn(1., eta, alpha_a, rho_t, delta_t, indices_t, a_t, f_t)
                gamma_t = gamma_tp1
                indices_t = indices_tp1
                rho_tm1 = rho_t
            rewards[run_num, -1] = Parallel(n_jobs=-1)(delayed(evaluate_policy)(actor, tc, num_timesteps=1000) for _ in range(num_evaluation_runs))

        # Plot results:
        mean_eval_rewards = np.mean(rewards, axis=2)
        var_eval_rewards = np.var(rewards, axis=2)
        mean_rewards = np.mean(mean_eval_rewards, axis=0)
        sem_rewards = np.sqrt(np.sum(var_eval_rewards / num_evaluation_runs, axis=0)) / num_runs
        fig = plt.figure()
        ax = fig.add_subplot(111)
        x = np.array([evaluation_interval*i for i in range(num_timesteps // evaluation_interval + 1)])
        confs = sem_rewards * st.t.ppf((1.0 + 0.95) / 2, num_evaluation_runs - 1)
        label = '$\\alpha_a$:{}, $\\alpha_c$:{}, $\\alpha_w$:{}, $\\lambda_c$:{}, $\\eta$:{}{}'.format(alpha_a, alpha_c, alpha_w, lambda_c, eta, '(OffPAC)' if eta == 0. else '')
        ax.errorbar(x, mean_rewards, yerr=[confs, confs], label=label)
        plt.legend(loc='lower right')
        plt.title('Mountain Car')
        plt.xlabel('Timesteps')
        plt.ylabel('Total Reward')
        plt.ylim(-1000, 0)
        plt.savefig('total_rewards.png')
        self.assertGreater(mean_rewards[-1], -200)

    def test_low_variance_binary_ace_off_policy(self):
        num_runs = 2
        num_timesteps = 5000
        evaluation_interval = 1000
        num_evaluation_runs = 1
        rewards = np.zeros((num_runs, num_timesteps // evaluation_interval + 1, num_evaluation_runs))
        alpha_a = .01
        alpha_c = .05
        alpha_w = .0001
        lambda_c = 0.
        eta = 0.
        env = gym.make('MountainCar-v0').unwrapped
        env.seed(193981441)
        rng = env.np_random
        tc = TileCoder(np.array([env.observation_space.low, env.observation_space.high]).T, [5, 5], 8, True)
        for run_num in range(num_runs):
            fhat = BinaryFHat(tc.total_num_tiles, .01)
            actor = BinaryACE(env.action_space.n, tc.total_num_tiles)
            critic = BinaryTDC(tc.total_num_tiles, alpha_c, alpha_w, lambda_c)
            indices_t = tc.encode(env.reset())
            gamma_t = 0.
            for t in tqdm(range(num_timesteps)):
                if t % evaluation_interval == 0:
                    rewards[run_num, t // evaluation_interval] = Parallel(n_jobs=-1)(delayed(evaluate_policy)(actor, tc, num_timesteps=1000) for _ in range(num_evaluation_runs))
                a_t = rng.choice(env.action_space.n)
                s_tp1, r_tp1, terminal, _ = env.step(a_t)
                if terminal:
                    s_tp1 = env.reset()
                    gamma_tp1 = 0.
                else:
                    gamma_tp1 = 1.
                indices_tp1 = tc.encode(s_tp1)
                pi_t = actor.pi(indices_t)
                mu_t = np.ones(env.action_space.n) / env.action_space.n
                rho_t = pi_t[a_t] / mu_t[a_t]
                delta_t = r_tp1 + gamma_tp1 * critic.estimate(indices_tp1) - critic.estimate(indices_t)
                F_t = fhat.estimate(indices_t)
                critic.learn(delta_t, indices_t, gamma_t, indices_tp1, gamma_tp1, rho_t)
                actor.learn(1., eta, alpha_a, rho_t, delta_t, indices_t, a_t, F_t)
                fhat.learn(indices_tp1, gamma_tp1, indices_t, rho_tm1=rho_t, i_t=1.)
                gamma_t = gamma_tp1
                indices_t = indices_tp1
            rewards[run_num, -1] = Parallel(n_jobs=-1)(delayed(evaluate_policy)(actor, tc, num_timesteps=1000) for _ in range(num_evaluation_runs))
        # Plot results:
        mean_eval_rewards = np.mean(rewards, axis=2)
        var_eval_rewards = np.var(rewards, axis=2)
        mean_rewards = np.mean(mean_eval_rewards, axis=0)
        sem_rewards = np.sqrt(np.sum(var_eval_rewards / num_evaluation_runs, axis=0)) / num_runs
        fig = plt.figure()
        ax = fig.add_subplot(111)
        x = np.array([evaluation_interval*i for i in range(num_timesteps // evaluation_interval + 1)])
        confs = sem_rewards * st.t.ppf((1.0 + 0.95) / 2, num_evaluation_runs - 1)
        label = '$\\alpha_a$:{}, $\\alpha_c$:{}, $\\alpha_w$:{}, $\\lambda_c$:{}, $\\eta$:{}{}'.format(alpha_a, alpha_c, alpha_w, lambda_c, eta, '(OffPAC)' if eta == 0. else '')
        ax.errorbar(x, mean_rewards, yerr=[confs, confs], label=label)
        plt.legend(loc='lower right')
        plt.title('Mountain Car')
        plt.xlabel('Timesteps')
        plt.ylabel('Total Reward')
        plt.ylim(-1000, 0)
        plt.savefig('total_rewards.png')
        self.assertGreater(mean_rewards[-1], -300)


if __name__ == '__main__':
    unittest.main()
