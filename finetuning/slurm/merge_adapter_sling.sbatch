#!/bin/bash
# Simple SLING launcher for merging a PEFT adapter into a standalone model export.
# Submit with:
#   sbatch --export=ALL,ADAPTER_PATH="/d/hpc/projects/FRI/zm3587/arnes/runs/gams3-qlora-v100-main",MERGED_OUTPUT_DIR="/d/hpc/projects/FRI/zm3587/arnes/runs/gams3-qlora-merged" slurm/merge_adapter_sling.sbatch
#
# Optional overrides:
#   sbatch --export=ALL,MODEL_PATH="your/model-id",ADAPTER_PATH="...",MERGED_OUTPUT_DIR="..." slurm/merge_adapter_sling.sbatch
#   sbatch -w gwn08 --export=ALL,ADAPTER_PATH="...",MERGED_OUTPUT_DIR="..." slurm/merge_adapter_sling.sbatch

#SBATCH --job-name=gams3-merge-adapter
#SBATCH --output=/d/hpc/projects/FRI/zm3587/arnes/slurm/%x-%j.out
#SBATCH --error=/d/hpc/projects/FRI/zm3587/arnes/slurm/%x-%j.err
#SBATCH --partition=gpu
#SBATCH --nodelist=gwn[01-10]
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=128G
#SBATCH --time=24:00:00

set -euo pipefail

PROJECT_ROOT="/d/hpc/projects/FRI/zm3587/arnes"
PYTHON_BIN="/d/hpc/home/zm3587/.conda/envs/arnes/bin/python"

: "${MODEL_PATH:=cjvt/GaMS3-12B-Instruct}"
: "${ADAPTER_PATH:?Set ADAPTER_PATH to the trained adapter directory.}"
: "${MERGED_OUTPUT_DIR:?Set MERGED_OUTPUT_DIR to the standalone merged model export directory.}"
: "${MERGE_DTYPE:=bfloat16}"

cd "$PROJECT_ROOT"
mkdir -p "$MERGED_OUTPUT_DIR" "$PROJECT_ROOT/slurm" "$PROJECT_ROOT/.cache/huggingface"

export MODEL_PATH
export ADAPTER_PATH
export MERGED_OUTPUT_DIR
export HF_HOME="$PROJECT_ROOT/.cache/huggingface"
export TOKENIZERS_PARALLELISM=false
export PYTHONNOUSERSITE=1
export PIP_NO_USER=1

echo "WORKDIR=$PROJECT_ROOT"
echo "MODEL_PATH=$MODEL_PATH"
echo "ADAPTER_PATH=$ADAPTER_PATH"
echo "MERGED_OUTPUT_DIR=$MERGED_OUTPUT_DIR"
echo "MERGE_DTYPE=$MERGE_DTYPE"
echo "HF_HOME=$HF_HOME"
echo "PYTHON_BIN=$PYTHON_BIN"
echo "HOSTNAME=$(hostname)"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-unset}"

"$PYTHON_BIN" -u "$PROJECT_ROOT/scripts/merge_adapter.py" --base-model "$MODEL_PATH" --adapter-path "$ADAPTER_PATH" --output-dir "$MERGED_OUTPUT_DIR" --dtype "$MERGE_DTYPE"
