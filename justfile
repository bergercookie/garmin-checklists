# Task runner for the Checklists project. `just` on its own lists everything.
#
# Recipes of your own go in `justfile.user`, which is not tracked by git and is
# imported below if it exists. See the bottom of this file.
set shell := ["bash", "-euo", "pipefail", "-c"]

root := justfile_directory()
bridge := root / "bridge"
# Override with `CIQ_DEVICE=descentg2 just watch-build`.
device := env_var_or_default("CIQ_DEVICE", "fenix7")

default:
    @just --list

# Recipes live in just/, grouped by subject. Imports are required: a missing
# file should stop the build rather than quietly lose half the recipes.
#
# Note that a recipe defined in an imported file runs with its working
# directory set to that file's directory, not this one -- which is why the
# recipes below spell paths out from `root` rather than relying on `pwd`.
import 'just/bridge.just'
import 'just/docs.just'
import 'just/container.just'
import 'just/watch.just'
import 'just/e2e.just'
import 'just/meta.just'

# ------------------------------------------------------------------- yours
# Optional, untracked, and yours: put personal recipes in `justfile.user` and
# they join the list above. `justfile.user.example` is a starting point.
#
# It can only *add* recipes. Reusing a name here is an error rather than a
# silent override, so `just lint` means the same thing on your machine as it
# does in CI.
import? 'justfile.user'
