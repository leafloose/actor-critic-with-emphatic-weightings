import os
import stat
import time
import argparse
import itertools
import numpy as np
from pathlib import Path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(fromfile_prefix_chars='@', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    # Experiment parameters:
    parser.add_argument('--output_dir', type=str, default='experiment', help='The directory to write experiment files to')
    parser.add_argument('--experience_file', type=str, default='experience.npy', help='The file to read experience from')
    parser.add_argument('--num_cpus', type=int, default=-1, help='The number of cpus to use (-1 for all).')

    parser.add_argument('--num_runs', type=int, default=5, help='The number of independent runs to do')
    parser.add_argument('--checkpoint_interval', type=int, default=5000, help='The number of timesteps after which to save the learned policy.')
    parser.add_argument('--num_evaluation_runs', type=int, default=5, help='The number of times to evaluate each policy')
    parser.add_argument('--max_timesteps', type=int, default=5000, help='The maximum number of timesteps allowed per policy evaluation')
    parser.add_argument('--random_seed', type=int, default=735026919, help='The master random seed to use')

    parser.add_argument('--script_name', type=str, default='run_ace.py', help='The script to run on each node.')
    parser.add_argument('--interest_function', type=str, default='lambda s, g=1: 1.', help='Interest function to use. Example: \'lambda s, g=1: 1. if g==0. else 0.\' (episodic interest function)')
    parser.add_argument('--behaviour_policy', type=str, default='lambda s: np.ones(env.action_space.n)/env.action_space.n', help='Policy to use. Default is uniform random. Another Example: \'lambda s: np.array([.9, .05, .05]) if s[1] < 0 else np.array([.05, .05, .9]) \' (energy pumping policy w/ 15 percent randomness)')
    parser.add_argument('--environment', type=str, default='MountainCar-v0', help='An OpenAI Gym environment string.')
    parser.add_argument('--gamma', '--discount_rate', type=float, default=.99, help='Discount rate.')
    parser.add_argument('--alpha_a', type=float, nargs='+', default=[1/2**i for i in range(11)], help='Step sizes for the actor.')
    parser.add_argument('--alpha_w', type=float, nargs='+', default=[1/2**i for i in range(11)], help='Step sizes for the critic.')
    parser.add_argument('--alpha_v', type=float, nargs='+', default=[1/2**i for i in range(11)], help='Step sizes for the critic\'s auxiliary weights.')
    parser.add_argument('--lambda_c', type=float, nargs='+', default=[(1 - 1/2**i) for i in range(6)], help='Trace decay rates for the critic.')
    parser.add_argument('--eta', type=float, nargs='+', default=[1.], help='OffPAC/ACE tradeoff parameter.')
    parser.add_argument('--num_tiles_per_dim', type=int, nargs='+', default=[5, 5], help='The number of tiles per dimension to use in the tile coder.')
    parser.add_argument('--num_tilings', type=int, default=8, help='The number of tilings to use in the tile coder.')
    parser.add_argument('--bias_unit', type=int, choices=[0, 1], default=1, help='Whether or not to include a bias unit in the tile coder.')

    # Script parameters:
    parser.add_argument('--seconds_per_combination', type=int, default=30, help='Predicted time in seconds a single parameter combination will take to run once. To estimate this, run the experiment script with 1 CPU and a reduced number of combinations and time it.')
    parser.add_argument('--num_hours', type=int, default=1, help='Number of hours the job should run for. On Niagara consider using one of: 1, 3, 12, 24.')
    parser.add_argument('--email', type=str, default='graves@ualberta.ca', help='Email address to report updates to.')
    parser.add_argument('--account', type=str, default='def-sutton', help='Allocation string to use in slurm.')
    parser.add_argument('--cores_per_node', type=int, default=40, help='Number of cores per node on the cluster. Niagara is 40.')
    args = parser.parse_args()

    # Calculate how many nodes to use:
    parameters = [args.alpha_a, args.alpha_w, args.alpha_v, args.lambda_c, args.eta]
    combinations = list(itertools.product(*parameters))
    core_hours = args.seconds_per_combination * len(combinations) * args.num_runs / 3600  # how long it would take 1 core to do the entire job.
    node_hours = core_hours / args.cores_per_node  # how long it would take 1 node to do the entire job.
    num_nodes = int(np.ceil(node_hours / args.num_hours))  # how many nodes it would take to do the entire job in the given amount of time.

    # Confirm the number of nodes is ok:
    if input(f'It would take 1 core approximately {core_hours} hours to do {args.num_runs} runs of {len(combinations)} combinations at {args.seconds_per_combination} seconds per combination.\nIt would take 1 node with {args.cores_per_node} cores approximately {node_hours} hours to do the entire job.\n{num_nodes} nodes would be required for the sweep to take {args.num_hours} hours.\nContinue generating scripts? y/[n]: ') != 'y':
        exit(0)

    # Generate the scripts:
    output_dir = Path(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)
    node_configs = np.array_split(combinations, num_nodes)  # Split the combinations evenly-ish across nodes.
    script_names = []
    for script_num, node_config in enumerate(node_configs):
        parameters_string = ' \\\n-p '.join([' '.join([str(p) for p in config]) for config in node_config])
        script_name = f'sweep{script_num}.sh'
        script_names.append(script_name)
        script = f'''#!/bin/bash
#SBATCH --mail-user={args.email}
#SBATCH --mail-type=ALL
#SBATCH --account={args.account}
#SBATCH --job-name=sweep{script_num}
#SBATCH --nodes=1
#SBATCH --cpus-per-task={args.cores_per_node}
#SBATCH --time=00-{args.num_hours}:00:00  # DD-HH:MM:SS
module load python/3.6.5
source ../../ve/bin/activate
python ../../{args.script_name} \\
--output_dir \'sweep{script_num}\' \\
--experience_file \'{args.experience_file}\' \\
--num_cpus {args.num_cpus} \\
--checkpoint_interval {args.checkpoint_interval} \\
--num_evaluation_runs {args.num_evaluation_runs} \\
--max_timesteps {args.max_timesteps} \\
--random_seed {args.random_seed} \\
--interest_function \'{args.interest_function}\' \\
--behaviour_policy \'{args.behaviour_policy}\' \\
--environment \'{args.environment}\' \\
--gamma {args.gamma} \\
--num_tiles_per_dim {' '.join(str(i) for i in args.num_tiles_per_dim)} \\
--num_tilings {args.num_tilings} \\
--bias_unit {args.bias_unit} \\
-p {parameters_string}
'''
        # Write the script to file:
        file_name = output_dir / script_name
        with open(file_name, 'w') as script_file:
            script_file.write(script)
            os.chmod(file_name, os.stat(file_name).st_mode | stat.S_IEXEC)  # Make script executable.

    if input('Schedule jobs now? y/[n]: ') != 'y':
        exit(0)

    os.chdir(args.output_dir)
    for script_name in script_names:
        os.system(f'sbatch {script_name}')
        time.sleep(1)
