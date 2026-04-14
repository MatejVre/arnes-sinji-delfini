#!/bin/bash
# Simple SLING launcher for baseline vs synthetic-adapter comparison.
# Submit with:
#   sbatch -w gwn08 slurm/evaluate_models_synthetic_sling.sbatch
#
# Optional override:
#   sbatch -w gwn08 --export=ALL,MODEL_PATH="your/model-id" slurm/evaluate_models_synthetic_sling.sbatch

#SBATCH --job-name=gams3-compare-synth
#SBATCH --output=/d/hpc/projects/FRI/zm3587/arnes/slurm/%x-%j.out
#SBATCH --error=/d/hpc/projects/FRI/zm3587/arnes/slurm/%x-%j.err
#SBATCH --partition=gpu
#SBATCH --nodelist=gwn[01-10]
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=128G
#SBATCH --time=04:00:00

set -euo pipefail

PROJECT_ROOT="/d/hpc/projects/FRI/zm3587/arnes"
PYTHON_BIN="/d/hpc/home/zm3587/.conda/envs/arnes/bin/python"

: "${MODEL_PATH:=cjvt/GaMS3-12B-Instruct}"
: "${QLORA_ADAPTER_PATH:=$PROJECT_ROOT/runs/gams3-qlora-v100-synthetic}"
: "${LORA_ADAPTER_PATH:=$PROJECT_ROOT/runs/gams3-lora-h100-synthetic}"
: "${OUTPUT_DIR:=$PROJECT_ROOT/runs/model-comparison-reviewed-synthetic}"
: "${CONFIG_FILE:=configs/model_comparison_reviewed.yaml}"

cd "$PROJECT_ROOT"
mkdir -p "$OUTPUT_DIR" "$PROJECT_ROOT/slurm" "$PROJECT_ROOT/.cache/huggingface"

export MODEL_PATH
export QLORA_ADAPTER_PATH
export LORA_ADAPTER_PATH
export OUTPUT_DIR
export CONFIG_FILE
export HF_HOME="$PROJECT_ROOT/.cache/huggingface"
export TOKENIZERS_PARALLELISM=false
export PYTHONNOUSERSITE=1
export PIP_NO_USER=1

echo "WORKDIR=$PROJECT_ROOT"
echo "MODEL_PATH=$MODEL_PATH"
echo "QLORA_ADAPTER_PATH=$QLORA_ADAPTER_PATH"
echo "LORA_ADAPTER_PATH=$LORA_ADAPTER_PATH"
echo "OUTPUT_DIR=$OUTPUT_DIR"
echo "CONFIG_FILE=$CONFIG_FILE"
echo "HF_HOME=$HF_HOME"
echo "PYTHON_BIN=$PYTHON_BIN"
echo "HOSTNAME=$(hostname)"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-unset}"

"$PYTHON_BIN" -u "$PROJECT_ROOT/scripts/evaluate_models.py" --config "$CONFIG_FILE"
