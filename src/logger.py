import qi
import inspect
import os

# Define log levels from qi.logging for convenience
FATAL = qi.logging.FATAL
ERROR = qi.logging.ERROR
WARNING = qi.logging.WARNING
INFO = qi.logging.INFO
VERBOSE = qi.logging.VERBOSE

# Add our own DEBUG level constant - use a higher number than VERBOSE for our internal logic
DEBUG = VERBOSE + 1  # Although qi.logging does not have a DEBUG level, we define it for our own use

# Define context bit flags
CONTEXT_VERBOSITY = 1
CONTEXT_SHORT_VERBOSITY = 2
CONTEXT_SYSTEM_DATE = 4
CONTEXT_THREAD_ID = 8
CONTEXT_CATEGORY = 16
CONTEXT_FILE = 32
CONTEXT_FUNCTION = 64
CONTEXT_END_OF_LINE = 128
CONTEXT_DATE = 256

# Global variable to track our current log level for debug/verbose filtering
_current_log_level = INFO

def setup_logging(level=INFO):
    """
    Configures the qi.logging service.
    Should be called once at the start of the application.
    """
    global _current_log_level
    _current_log_level = level
    
    # Set a single, fixed context for all log levels.
    # Format: [L] filename.py [lineno]: message
    context = CONTEXT_SHORT_VERBOSITY | CONTEXT_CATEGORY
    qi.logging.setContext(context)
    
    # For qi.logging, map our DEBUG level to VERBOSE since qi doesn't have DEBUG
    qi_level = min(level, VERBOSE)  # Cap at VERBOSE (5) for qi.logging
    qi.logging.setLevel(qi_level)
    info("Logger: qi.logging service configured with level=%d (qi_level=%d)", level, qi_level)

def set_filters(filter_string):
    """
    Set logging filters using qi.logging filter syntax.
    
    Args:
        filter_string (str): Filter rules separated by colon. 
                           Examples: "+CAT", "-CAT", "CAT=level", "qi.*=verbose:-qi.foo:+qi.foo.bar"
    """
    if filter_string:
        qi.logging.setFilters(filter_string)
        info("Logger: Applied filters: %s", filter_string)

def _get_category():
    """
    Inspects the call stack to find the filename of the caller.
    Returns only the filename without line number for consistent qi.logging context.
    """
    try:
        stack = inspect.stack()
        # stack[0] is _get_category, stack[1] is the log function, stack[2] is the caller.
        for frame_record in stack[2:]:
            # Find the first frame outside of this logger module
            if frame_record[1] != __file__:
                filename = os.path.basename(frame_record[1])
                # Python 2.7 compatible string formatting - return only filename
                return filename
        return "unknown"
    except IndexError:
        return "unknown"

def _get_line_number():
    """
    Inspects the call stack to find the line number of the caller.
    """
    try:
        stack = inspect.stack()
        # stack[0] is _get_line_number, stack[1] is _format_message, stack[2] is the log function, stack[3] is the caller.
        for frame_record in stack[3:]:
            # Find the first frame outside of this logger module
            if frame_record[1] != __file__:
                lineno = frame_record[2]
                return lineno
        return 0
    except IndexError:
        return 0

def _format_message(msg):
    """
    Format message with line number in bold at the start.
    """
    line_number = _get_line_number()
    
    # Add bold line number at start of message
    formatted_msg = "\033[1m[%d]\033[0m %s" % (line_number, msg)

    return formatted_msg

def fatal(msg, *args):
    """Logs a message with level FATAL."""
    qi.logging.fatal(_get_category(), _format_message(msg), *args)

def error(msg, *args):
    """Logs a message with level ERROR."""
    qi.logging.error(_get_category(), _format_message(msg), *args)

def warning(msg, *args):
    """Logs a message with level WARNING."""
    qi.logging.warning(_get_category(), _format_message(msg), *args)

def info(msg, *args):
    """Logs a message with level INFO."""
    qi.logging.info(_get_category(), _format_message(msg), *args)

def verbose(msg, *args):
    """Logs a message with level VERBOSE - most detailed level, shows when level is VERBOSE only."""
    # Only log if current level is exactly VERBOSE (most detailed)
    if _current_log_level == VERBOSE:
        qi.logging.verbose(_get_category(), _format_message(msg), *args)

def debug(msg, *args):
    """Logs a message with level DEBUG - shows when level is DEBUG or higher (but not VERBOSE)."""
    # Only log if current level is DEBUG or higher, but NOT VERBOSE
    if _current_log_level >= DEBUG and _current_log_level != VERBOSE:
        # Map debug to qi.logging.verbose since qi doesn't have debug level
        qi.logging.verbose(_get_category(), _format_message(msg), *args)