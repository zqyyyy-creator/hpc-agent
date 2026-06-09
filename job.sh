#!/bin/bash
#SBATCH --job-name=agent_test
#SBATCH --partition=amd_test
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:01:00
#SBATCH --output=agent_%j.out
#SBATCH --error=agent_%j.err

hostname
date
