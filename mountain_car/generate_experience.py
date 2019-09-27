import os
import gym
import random
import argparse
import numpy as np
from pathlib import Path
from joblib import Parallel, delayed

# TODO: Figure out how to do checkpointing (i.e. keep track of progress via a memmap so if the process gets killed it can pick up where it left off).
# TODO: Figure out how to append to a memmap in case we want to do more runs later on (we might get this without any extra work with checkpointing).
# TODO: Move to JSON (away from argparse format) for experiment configuration?

transition_dtype = np.dtype([('s_t', float, (2,)), ('a_t', int, 1), ('r_tp1', float, 1), ('s_tp1', float, (2,)), ('terminal', bool, 1)])


def generate_experience(experience, run_num, num_timesteps, random_seed):
    
    # Initialize the environment:
    env = gym.make('MountainCar-v0').env  # Get the underlying environment object to bypass the built-in timestep limit.

    # Configure random state for the run:
    env.seed(random_seed)
    rng = env.np_random
    
    # Generate the required timesteps of experience:
    transitions = np.empty(num_timesteps, dtype=transition_dtype)
    s_t = env.reset()
    for t in range(num_timesteps):

        # Select an action:
        a_t = rng.choice(env.action_space.n) # equiprobable random policy

        # Take action a_t, observe next state s_tp1 and reward r_tp1:
        s_tp1, r_tp1, terminal, _ = env.step(a_t)

        # The agent is reset to a starting state after a terminal transition:
        if terminal:
            s_tp1 = env.reset()

        # Add the transition:
        transitions[t] = (s_t, a_t, s_tp1, r_tp1, terminal)

        # Update temporary variables:
        s_t = s_tp1

    # Write the generated transitions to file:
    experience[run_num] = transitions


if __name__ == '__main__':

    # Parse command line arguments:
    parser = argparse.ArgumentParser(description='A script to generate experience from a uniform random policy on the Mountain Car environment in parallel.', fromfile_prefix_chars='@')
    parser.add_argument('--experiment_name', type=str, default='experiment', help='The directory to write experiment files to')
    parser.add_argument('--num_runs', type=int, default=5, help='The number of independent runs of experience to generate')
    parser.add_argument('--num_timesteps', type=int, default=100000, help='The number of timesteps of experience to generate per run')
    parser.add_argument('--random_seed', type=int, default=3139378768, help='The master random seed to use')
    parser.add_argument('--num_cpus', type=int, default=-1, help='The number of cpus to use (-1 means all)')
    parser.add_argument('--backend', type=str, default='loky', help='The backend to use (\'loky\' for processes or \'threading\' for threads). Always use \'loky\' lol')
    args = parser.parse_args()

    # Generate the random seed for each run without replacement:
    random.seed(args.random_seed)
    random_seeds = random.sample(range(2**32), args.num_runs)

    # Create the output directory:
    experiment_path = Path(args.experiment_name)
    os.makedirs(experiment_path, exist_ok=True)

    # Save the command line arguments in a format interpretable by argparse:
    with open(experiment_path / Path(parser.prog).with_suffix('.args'), 'w') as args_file:
        for key, value in vars(args).items():
            args_file.write('--{}\n{}\n'.format(key, value))

    # Create the memmapped array of experience to be populated in parallel:
    experience = np.memmap(experiment_path / 'experience.npy', shape=(args.num_runs, args.num_timesteps), dtype=transition_dtype, mode='w+')

    # Generate the experience in parallel:
    Parallel(n_jobs=args.num_cpus, verbose=10, backend=args.backend)(
        delayed(generate_experience)(experience, run_num, args.num_timesteps, random_seed) for run_num, random_seed in
        enumerate(random_seeds))

    # Close the memmap file:
    del experience