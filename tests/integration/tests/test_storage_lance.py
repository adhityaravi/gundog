"""Test module for LanceDB storage feature."""

from pytest_bdd import scenarios

# Load all scenarios from the lance storage feature file
scenarios("../features/storage_lance.feature")
