#!/bin/bash
# Simple SLING launcher for the reviewed-data QLoRA run on V100S.
# Submit with:
#   sbatch -p gpu slurm/train_qlora_reviewed_sling.sbatch
#
# Optional overrides:
#   sbatch -p gpu --export=ALL,MODEL_PATH="your/model-id" slurm/train_qlora_reviewed_sling.sbatch
#   sbatch -p gpu --export=ALL,OUTPUT_DIR="/d/hpc/projects/FRI/zm3587/arnes/runs/my-run" slurm/train_qlora_reviewed_sling.sbatch

#SBATCH --job-name=gams3-qlora-reviewed
#SBATCH --output=/d/hpc/projects/FRI/zm3587/arnes/slurm/%x-%j.out
#SBATCH --error=/d/hpc/projects/FRI/zm3587/arnes/slurm/%x-%j.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=64G
#SBATCH --time=08:00:00

set -euo pipefail

PROJECT_ROOT="/d/hpc/projects/FRI/zm3587/arnes"
PYTHON_BIN="/d/hpc/home/zm3587/.conda/envs/arnes/bin/python"

: "${MODEL_PATH:=cjvt/GaMS3-12B-Instruct}"
: "${OUTPUT_DIR:=$PROJECT_ROOT/runs/gams3-qlora-v100-main}"
: "${CONFIG_FILE:=configs/qlora_gams3_12b_instruct_reviewed_fp16_v100.yaml}"

cd "$PROJECT_ROOT"
mkdir -p "$OUTPUT_DIR" "$PROJECT_ROOT/slurm" "$PROJECT_ROOT/.cache/huggingface"

export MODEL_PATH
export OUTPUT_DIR
export CONFIG_FILE
export HF_HOME="$PROJECT_ROOT/.cache/huggingface"
export TOKENIZERS_PARALLELISM=false
export PYTHONNOUSERSITE=1
export PIP_NO_USER=1

echo "WORKDIR=$PROJECT_ROOT"
echo "MODEL_PATH=$MODEL_PATH"
echo "OUTPUT_DIR=$OUTPUT_DIR"
echo "CONFIG_FILE=$CONFIG_FILE"
echo "HF_HOME=$HF_HOME"
echo "PYTHON_BIN=$PYTHON_BIN"
echo "HOSTNAME=$(hostname)"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-unset}"

"$PYTHON_BIN" -u "$PROJECT_ROOT/scripts/train_qlora.py" --config "$CONFIG_FILE"
