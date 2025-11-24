# To install just on a per-project basis
# 1. Activate your virtual environemnt
# 2. uv add --dev rust-just
# 3. Use just within the activated environment

drive_uuid := "77688511-78c5-4de3-9108-b631ff823ef4"
#drive_uuid := "8425-155D"

user :=  file_stem(home_dir())
def_drive := join("/media", user, drive_uuid)
project := file_stem(justfile_dir())
local_env := join(justfile_dir(), ".env")


# list all recipes
default:
    just --list

# Install tools globally
tools:
    uv tool install twine
    uv tool install ruff

# Add conveniente development dependencies
dev:
    uv add --dev pytest

# Build the package
build:
    rm -fr dist/*
    uv build

# Generate a requirements file
requirements:
    uv pip compile pyproject.toml -o requirements.txt

# Publish the package to PyPi
publish pkg=project mod="tessdb": build
    twine upload -r pypi dist/*
    uv run --no-project --with {{pkg}} --refresh-package {{pkg}} \
        -- python -c "from {{mod}} import __version__; print(__version__)"

# Publish to Test PyPi server
test-publish pkg=project mod="tessdb": build
    twine upload --verbose -r testpypi dist/*
    uv run --no-project  --with {{pkg}} --refresh-package {{pkg}} \
        --index-url https://test.pypi.org/simple/ \
        --extra-index-url https://pypi.org/simple/ \
        -- python -c "from {{mod}} import __version__; print(__version__)"


# upgrades library and uv.lock
upgrade library:
    uv pip install --upgrade {{library}}
    uv lock --upgrade

pull:
    git pull --rebase --tags

push:
    git push --tags

run mode="dev":
    #!/usr/bin/env bash
    set -exuo pipefail
    uv run tess-publisher --console --trace --config config.toml



# Backup .env to storage unit
env-bak drive=def_drive: (check_mnt drive) (env-backup join(drive, "env", project))

# Restore .env from storage unit
env-rst drive=def_drive: (check_mnt drive) (env-restore join(drive, "env", project))


# =============
# PyTest driver
# =============

test pkg module:
    uv run pytest tests/{{pkg}}/test_{{module}}.py

testf pkg module func:
    uv run pytest tests/{{pkg}}/test_{{module}}.py::test_{{func}}


# ================ #
# HTTP API TESTING #
# ================ #

hello port="8080":
    #!/usr/bin/env bash   
    set -euo pipefail
    response=$(curl -s -X GET http://localhost:{{port}}/v1)
    echo $response
    
stats port="8080":
    #!/usr/bin/env bash   
    set -euo pipefail
    response=$(curl -s -X GET http://localhost:{{port}}/v1/stats)
    echo $response


pause port="8080":
    #!/usr/bin/env bash   
    set -euo pipefail
    response=$(curl -s -X POST http://localhost:{{port}}/v1/server/pause -d '{}' -H "Content-Type: application/json")
    echo $response
    
resume port="8080":
    #!/usr/bin/env bash   
    set -euo pipefail
    response=$(curl -s -X POST http://localhost:{{port}}/v1/server/resume -d '{}' -H "Content-Type: application/json")
    echo $response

reload port="8080":
    #!/usr/bin/env bash   
    set -euo pipefail
    response=$(curl -s -X POST http://localhost:{{port}}/v1/server/reload -d '{}' -H "Content-Type: application/json")
    echo $response


# =======================================================================

[private]
check_mnt mnt:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ ! -d  {{ mnt }} ]]; then
        echo "Drive not mounted: {{ mnt }}"
        exit 1 
    fi

[private]
env-backup bak_dir:
    #!/usr/bin/env bash
    set -exuo pipefail
    if [[ ! -f  {{ local_env }} ]]; then
        echo "Can't backup: {{ local_env }} doesn't exists"
        exit 1 
    fi
    mkdir -p {{ bak_dir }}
    cp {{ local_env }} {{ bak_dir }}
    cp config.toml {{ bak_dir }}
  
[private]
env-restore bak_dir:
    #!/usr/bin/env bash
    set -euxo pipefail
    if [[ ! -f  {{ bak_dir }}/.env ]]; then
        echo "Can't restore: {{ bak_dir }}/.env doesn't exists"
        exit 1 
    fi
    cp {{ bak_dir }}/.env {{ local_env }}
    cp {{ bak_dir }}/config.toml .
    
