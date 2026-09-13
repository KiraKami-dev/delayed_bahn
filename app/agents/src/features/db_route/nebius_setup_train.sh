apt-get update -qq && apt-get install -y -qq curl ca-certificates build-essential > /dev/null
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv venv --python 3.12 /workspace/.venv
uv pip install --python /workspace/.venv/bin/python torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cu130
uv pip install --python /workspace/.venv/bin/python -r /outputs/code/requirements_train.txt
# The setup runs inside run.sh, so this PATH reaches the `exec python` line that follows it.
# (A symlink to a venv python from another directory does not activate the venv.)
export PATH="/workspace/.venv/bin:$PATH"; hash -r
python -c "import sys, torch, opentslm, timenet; print('python', sys.version.split()[0], 'torch', torch.__version__, 'cuda', torch.cuda.is_available())"
