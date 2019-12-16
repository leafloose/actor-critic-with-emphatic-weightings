import gym
import gym_puddle
import argparse
import numpy as np
from pathlib import Path
from joblib import Parallel, delayed
from src import utils
from src.algorithms.ace import BinaryACE
from src.algorithms.tdc import BinaryTDC
from src.function_approximation.tile_coder import TileCoder


# TODO: Figure out how to do checkpointing (i.e. keep track of progress via a memmap so if the process gets killed it can pick up where it left off).
# TODO: Figure out how to append to a memmap in case we want to do more runs later on (we might get this without any extra work with checkpointing).


def run_ace(policies_memmap, experience_memmap, run_num, config_num, parameters):
    gamma, alpha_a, alpha_c, alpha_w, lambda_c, eta, num_tiles, num_tilings, num_features, bias_unit = parameters
    num_tiles = int(num_tiles)
    num_tilings = int(num_tilings)
    num_features = int(num_features)
    bias_unit = int(bias_unit)

    i = eval(args.interest_function)  # Create the interest function to use.
    mu = eval(args.behaviour_policy, {'np': np, 'env': env})  # Create the behaviour policy and give it access to numpy.

    tc = TileCoder(env.observation_space.low, env.observation_space.high, num_tiles, num_tilings, num_features, bias_unit)
    actor = BinaryACE(env.action_space.n, num_features)
    critic = BinaryTDC(num_features, alpha_c, alpha_w, lambda_c)

    policies = np.zeros(num_policies, dtype=policy_dtype)
    transitions = experience_memmap[run_num]  # Get the run of experience to learn from.
    gamma_t = 0.
    indices_t = tc.indices(transitions[0][0])
    for t, transition in enumerate(transitions):
        if t % args.checkpoint_interval == 0:  # Save the learned policy if it's a checkpoint timestep:
            padded_weights = np.zeros_like(policies[t // args.checkpoint_interval][1])
            padded_weights[0:actor.theta.shape[0], 0:actor.theta.shape[1]] = np.copy(actor.theta)
            policies[t // args.checkpoint_interval] = (t, padded_weights)

        # Unpack the stored transition.
        s_t, a_t, r_tp1, s_tp1, terminal = transition
        gamma_tp1 = gamma if not terminal else 0  # Transition-dependent discounting.
        indices_tp1 = tc.indices(s_tp1)
        i_t = i(s_t, gamma_t)
        # Compute importance sampling ratio for the policy:
        pi_t = actor.pi(indices_t)
        mu_t = mu(s_t)
        rho_t = pi_t[a_t] / mu_t[a_t]
        # Compute TD error:
        v_t = critic.estimate(indices_t)
        v_tp1 = critic.estimate(indices_tp1)
        delta_t = r_tp1 + gamma_tp1 * v_tp1 - v_t
        # Update actor:
        actor.learn(gamma_t, i_t, eta, alpha_a, rho_t, delta_t, indices_t, a_t)
        # Update critic:
        critic.learn(delta_t, indices_t, gamma_t, indices_tp1, gamma_tp1, rho_t)

        gamma_t = gamma_tp1
        indices_t = indices_tp1

    # Save the policy after the final timestep:
    padded_weights = np.zeros_like(policies[-1][1])
    padded_weights[0:actor.theta.shape[0], 0:actor.theta.shape[1]] = np.copy(actor.theta)
    policies[-1] = (t+1, padded_weights)
    policies_memmap[run_num, config_num] = (gamma, alpha_a, alpha_c, alpha_w, lambda_c, eta, num_tiles, num_tilings, num_features, bias_unit, policies)


if __name__ == '__main__':

    # Parse command line arguments:
    parser = argparse.ArgumentParser(description='A script to run ACE (Actor-Critic with Emphatic weightings) in parallel.', fromfile_prefix_chars='@', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--experiment_name', type=str, default='experiment', help='The directory to read/write experiment files to/from')
    parser.add_argument('--checkpoint_interval', type=int, default=12500, help='The number of timesteps after which to save the learned policy.')
    parser.add_argument('--num_cpus', type=int, default=-1, help='The number of cpus to use (-1 for all).')
    parser.add_argument('--backend', type=str, choices=['loky', 'threading'], default='loky', help='The backend to use (\'loky\' for processes or \'threading\' for threads; always use \'loky\' because Python threading is terrible).')
    parser.add_argument('--interest_function', type=str, default='lambda s, g=1: 1.', help='Interest function to use. Example: \'lambda s, g=1: 1. if g==0. else 0.\' (episodic interest function)')
    parser.add_argument('--behaviour_policy', type=str, default='lambda s: np.ones(env.action_space.n)/env.action_space.n', help='Policy to use. Default is uniform random. Another Example: \'lambda s: np.array([.9, .05, .05]) if s[1] < 0 else np.array([.05, .05, .9]) \' (energy pumping policy w/ 15 percent randomness)')
    parser.add_argument('--environment', type=str, choices=['MountainCar-v0', 'Acrobot-v1', 'PuddleWorld-v0'], default='MountainCar-v0', help='The environment to run ACE on.')
    parser.add_argument('--parameters', required=True, type=float, nargs=10, action='append', metavar=('DISCOUNT_RATE', 'ACTOR_STEP_SIZE', 'CRITIC_STEP_SIZE', 'CRITIC_STEP_SIZE_2', 'CRITIC_TRACE_DECAY_RATE', 'OFFPAC_ACE_TRADEOFF', 'NUM_TILES', 'NUM_TILINGS', 'NUM_FEATURES', 'BIAS_UNIT'), help='Parameters to use for ACE. Can be specified multiple times to run multiple configurations of ACE at once. Example:\n--parameters .99 .01 .05 .0001 .0 .0 9 9 10000 1.')
    args = parser.parse_args()

    # Save the command line arguments in a format interpretable by argparse:
    experiment_path = Path(args.experiment_name)
    utils.save_args_to_file(args, experiment_path / Path(parser.prog).with_suffix('.args'))

    # Load the input data as a memmap to prevent a copy being loaded into memory in each sub-process:
    experience_memmap = np.lib.format.open_memmap(str(experiment_path / 'experience.npy'), mode='r')
    num_runs, num_timesteps = experience_memmap.shape

    # Create the memmapped array of learned policies that will be populated in parallel:
    env = gym.make(args.environment).env  # Make a dummy env to get shape info.
    num_policies = num_timesteps // args.checkpoint_interval + 1
    max_num_features = int(max(parameters[8] for parameters in args.parameters))
    policy_dtype = np.dtype(
        [
            ('timestep', int),
            ('weights', float, (env.action_space.n, max_num_features))
        ]
    )
    configuration_dtype = np.dtype(
        [
            ('gamma', float),
            ('alpha_a', float),
            ('alpha_c', float),
            ('alpha_c2', float),
            ('lambda_c', float),
            ('eta', float),
            ('num_tiles', int),
            ('num_tilings', int),
            ('num_features', int),
            ('bias_unit', bool),
            ('policies', policy_dtype, num_policies)
        ]
    )
    num_configurations = len(args.parameters)
    policies_memmap = np.lib.format.open_memmap(str(experiment_path / 'policies.npy'), shape=(num_runs, num_configurations), dtype=configuration_dtype, mode='w+')

    # Run ACE for each set of parameters in parallel:
    Parallel(n_jobs=args.num_cpus, verbose=10)(
        delayed(run_ace)(
            policies_memmap, experience_memmap,
            run_num, config_num, parameters
        )
        for config_num, parameters in enumerate(args.parameters)
        for run_num in range(num_runs)
    )

    # Close the memmap files:
    del experience_memmap
    del policies_memmap