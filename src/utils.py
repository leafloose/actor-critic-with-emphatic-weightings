import os
import joblib
import contextlib
import numpy as np
from tqdm import tqdm
import matplotlib.pyplot as plt
from joblib import Parallel, delayed
from mpl_toolkits.mplot3d import Axes3D


position_limits = np.array([-1.2, .6])
velocity_limits = np.array([-.07, .07])


def save_args_to_file(args, args_file_path):
    """
    Saves command line arguments to a file in a format interpretable by argparse (one 'word' per line).
    :param args: Namespace of command line arguments.
    :param args_file_path: Path to the file to save the arguments in.
    :return:
    """
    os.makedirs(args_file_path.parent, exist_ok=True)
    with open(args_file_path, 'w') as args_file:
        for key, value in vars(args).items():
            if key == 'parameters' and isinstance(value, list):  # Special case for 'parameters' argument.
                for plist in value:
                    args_file.write('--{}\n{}\n'.format(key, '\n'.join(str(i) for i in plist)))
            elif isinstance(value, list):
                value = ' '.join(str(i) for i in value)
                args_file.write('--{}\n{}\n'.format(key, value))
            else:
                args_file.write('--{}\n{}\n'.format(key, value))


def plot_learned_value_function(critic, tile_coder, num_samples_per_dimension=100):
    fig = plt.figure()
    ax = fig.gca(projection='3d')

    # Sample the learned value function:
    positions = np.linspace(*position_limits, num_samples_per_dimension)
    velocities = np.linspace(*velocity_limits, num_samples_per_dimension)
    value_estimates = np.zeros((num_samples_per_dimension, num_samples_per_dimension))
    for p, position in enumerate(positions):
        for v, velocity in enumerate(velocities):
            indices = tile_coder.indices((position, velocity))
            value_estimates[p, v] = critic.estimate(indices)

    pos, vel = np.meshgrid(positions, velocities)
    ax.plot_surface(pos, vel, value_estimates, cmap='hot')
    plt.title('Learned value function on the Mountain Car environment')
    plt.xlabel('Position')
    plt.xlim(position_limits)
    plt.ylabel('Velocity')
    plt.ylim(velocity_limits)
    plt.savefig('learned_value_function.png')
    plt.show()


def plot_learned_policy(actor, tile_coder, num_samples_per_dimension=100):
    fig = plt.figure()
    ax = fig.gca(projection='3d')

    # Sample the learned policy:
    positions = np.linspace(*position_limits, num_samples_per_dimension)
    velocities = np.linspace(*velocity_limits, num_samples_per_dimension)
    learned_policy = np.zeros((num_samples_per_dimension, num_samples_per_dimension, 3))
    for p, position in enumerate(positions):
        for v, velocity in enumerate(velocities):
            indices = tile_coder.indices((position, velocity))
            learned_policy[p, v] = actor.pi(indices)

    pos, vel = np.meshgrid(positions, velocities)
    ax.plot_surface(pos, vel, learned_policy[:, :, 2], cmap='hot')
    plt.title('Probability of action 2 in learned policy on the Mountain Car environment')
    plt.xlabel('Position')
    plt.xlim(position_limits)
    plt.ylabel('Velocity')
    plt.ylim(velocity_limits)
    plt.savefig('learned_policy.png')
    plt.show()


def plot_visits(transitions):
    fig = plt.figure()
    ax = fig.gca()
    states = []
    for transition in transitions:
        states.append(transition[0])  # Add the first state in every transition.
    states.append(transitions[-1][3])  # Add the last state in the last transition.
    states = np.array(states).T  # Convert to np.array.
    ax.plot(states[0], states[1])

    plt.title('State visits')
    plt.xlabel('Position')
    plt.xlim(position_limits)
    plt.ylabel('Velocity')
    plt.ylim(velocity_limits)
    plt.savefig('state_visits.png')
    plt.show()


@contextlib.contextmanager
def tqdm_joblib(tqdm_object):
    """Context manager to patch joblib to report into tqdm progress bar given as argument"""
    class TqdmBatchCompletionCallback:
        def __init__(self, time, index, parallel):
            self.index = index
            self.parallel = parallel

        def __call__(self, index):
            tqdm_object.update()
            if self.parallel._original_iterator is not None:
                self.parallel.dispatch_next()

    old_batch_callback = joblib.parallel.BatchCompletionCallBack
    joblib.parallel.BatchCompletionCallBack = TqdmBatchCompletionCallback
    try:
        yield tqdm_object
    finally:
        joblib.parallel.BatchCompletionCallBack = old_batch_callback
        tqdm_object.close()