#!/bin/bash

#SBATCH --account=def-sutton
#SBATCH --job-name=ace_mc_sweep
#SBATCH --mail-user=graves@ualberta.ca
#SBATCH --mail-type=ALL
#SBATCH --nodes=1
#SBATCH --cpus-per-task=80  # Change to 80 to use hyperthreading.
#SBATCH --time=00-01:00:00  # DD-HH:MM:SS

module load python/3.7

# Configure virtual environment locally:
virtualenv --no-download $SLURM_TMPDIR/ve
source $SLURM_TMPDIR/ve/bin/activate
pip install --no-index --upgrade pip
pip install --no-index -r $HOME/actor-critic-with-emphatic-weightings/requirements.txt

python $HOME/actor-critic-with-emphatic-weightings/generate_experience.py \
--experiment_name $SCRATCH/actor-critic-with-emphatic-weightings/ace_mc_sweep \
--num_runs 10 \
--num_timesteps 100000 \
--random_seed 3139378768 \
--num_cpus -1 \
--backend "loky" \
--verbosity 0 \
--behaviour_policy "lambda s: np.ones(env.action_space.n)/env.action_space.n" \
--environment "MountainCar-v0"

python $HOME/actor-critic-with-emphatic-weightings/run_ace.py \
--experiment_name $SCRATCH/actor-critic-with-emphatic-weightings/ace_mc_sweep \
--checkpoint_interval 5000 \
--num_cpus -1 \
--backend "loky" \
--verbosity 0 \
--interest_function "lambda s, g=1: 1." \
--behaviour_policy "lambda s: np.ones(env.action_space.n)/env.action_space.n" \
--environment "MountainCar-v0" \
--run_mode "combinations" \
--gamma 1.0 \
--alpha_a .00001 .00005 .0001 .0005 .001 .005 .01 .05 .1 \
--alpha_c .00001 .00005 .0001 .0005 .001 .005 .01 .05 .1 \
--alpha_c2 .0 .00001 .00005 .0001 .0005 .001 .005 .01 .05 .1 \
--lambda_c .0 .4 .7 .9 .99 \
--eta 0. 1. \
--num_tiles 9 \
--num_tilings 9 \
--num_features 100000 \
--bias_unit 1

python $HOME/actor-critic-with-emphatic-weightings/evaluate_policies.py \
--experiment_name $SCRATCH/actor-critic-with-emphatic-weightings/ace_mc_sweep \
--num_evaluation_runs 5 \
--max_timesteps 1000 \
--random_seed 1944801619 \
--num_cpus -1 \
--backend "loky" \
--verbosity 0 \
--objective "episodic" \
--environment "MountainCar-v0"
