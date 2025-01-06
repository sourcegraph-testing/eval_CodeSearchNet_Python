"""
Status codes for a simulation (the stages of the simulation script).
"""

READY_TO_RUN   = 'ready'
STARTED_SCRIPT = 'start'
STAGING_INPUT  = 'input'
RUNNING_MODEL  = 'model'
STAGING_OUTPUT = 'output'
OUTPUT_ERROR   = 'out:err'
SCRIPT_DONE    = 'done'
SCRIPT_ERROR   = 'error'

MAX_LENGTH = 7

ALL = (
    READY_TO_RUN,
    STARTED_SCRIPT,
    STAGING_INPUT,
    RUNNING_MODEL,
    STAGING_OUTPUT,
    OUTPUT_ERROR,
    SCRIPT_DONE,
    SCRIPT_ERROR,
)


def is_valid(status_code):
    """
    Is a status code valid (known)?
    """
    return status_code in ALL


_descriptions = {
    READY_TO_RUN:   'ready to run',
    STARTED_SCRIPT: 'script started',
    STAGING_INPUT:  'staging input files',
    RUNNING_MODEL:  'running model',
    STAGING_OUTPUT: 'processing output files',
    OUTPUT_ERROR:   'error transmitting output',
    SCRIPT_DONE:    'script done',
    SCRIPT_ERROR:   'error occurred',
}


def get_description(status_code):
    """
    Get the description for a status code.
    """
    description = _descriptions.get(status_code)
    if description is None:
        description = 'code = %s (no description)' % str(status_code)
    return description