import qi
import inspect
import os
import sys

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
        # Use sys._getframe instead of inspect.stack() for Python 2.7 compatibility
        frame = sys._getframe(2)  # Go up 2 frames to get the actual caller
        while frame:
            filename = frame.f_code.co_filename
            if filename != __file__:
                return os.path.basename(filename)
            frame = frame.f_back
        return "unknown"
    except (AttributeError, ValueError):
        # Fallback if _getframe is not available or fails
        return "unknown"

def _get_line_number():
    """
    Inspects the call stack to find the line number of the caller.
    """
    try:
        # Use sys._getframe instead of inspect.stack() for Python 2.7 compatibility
        frame = sys._getframe(3)  # Go up 3 frames to get the actual caller
        while frame:
            filename = frame.f_code.co_filename
            if filename != __file__:
                return frame.f_lineno
            frame = frame.f_back
        return 0
    except (AttributeError, ValueError):
        # Fallback if _getframe is not available or fails
        return 0

def _format_message(msg, *args):
    """
    Format message with arguments and line number.
    """
    try:
        line_number = _get_line_number()
        # Format the message with arguments first
        if args:
            formatted_msg = msg % args
        else:
            formatted_msg = str(msg)
        # Add bold line number at start of message
        final_msg = "\033[1m[%d]\033[0m %s" % (line_number, formatted_msg)
        return final_msg
    except Exception:
        # Fallback to simple formatting if anything goes wrong
        if args:
            return str(msg % args)
        else:
            return str(msg)

def fatal(msg, *args):
    """Logs a message with level FATAL."""
    try:
        formatted_msg = _format_message(msg, *args)
        qi.logging.fatal(_get_category(), formatted_msg)
    except Exception:
        # Fallback to simple print if qi.logging fails
        try:
            fallback_msg = msg % args if args else str(msg)
        except:
            fallback_msg = str(msg) + " " + " ".join(str(arg) for arg in args)
        print("FATAL [%s]: %s" % (_get_category(), fallback_msg))

def error(msg, *args):
    """Logs a message with level ERROR."""
    try:
        formatted_msg = _format_message(msg, *args)
        qi.logging.error(_get_category(), formatted_msg)
    except Exception:
        # Fallback to simple print if qi.logging fails
        try:
            fallback_msg = msg % args if args else str(msg)
        except:
            fallback_msg = str(msg) + " " + " ".join(str(arg) for arg in args)
        print("ERROR [%s]: %s" % (_get_category(), fallback_msg))

def warning(msg, *args):
    """Logs a message with level WARNING."""
    try:
        formatted_msg = _format_message(msg, *args)
        qi.logging.warning(_get_category(), formatted_msg)
    except Exception:
        # Fallback to simple print if qi.logging fails
        try:
            fallback_msg = msg % args if args else str(msg)
        except:
            fallback_msg = str(msg) + " " + " ".join(str(arg) for arg in args)
        print("WARNING [%s]: %s" % (_get_category(), fallback_msg))

def info(msg, *args):
    """Logs a message with level INFO."""
    try:
        formatted_msg = _format_message(msg, *args)
        qi.logging.info(_get_category(), formatted_msg)
    except Exception:
        # Fallback to simple print if qi.logging fails
        try:
            fallback_msg = msg % args if args else str(msg)
        except:
            fallback_msg = str(msg) + " " + " ".join(str(arg) for arg in args)
        print("INFO [%s]: %s" % (_get_category(), fallback_msg))

def verbose(msg, *args):
    """Logs a message with level VERBOSE - most detailed level, shows when level is VERBOSE only."""
    # Only log if current level is exactly VERBOSE (most detailed)
    if _current_log_level == VERBOSE:
        try:
            formatted_msg = _format_message(msg, *args)
            qi.logging.verbose(_get_category(), formatted_msg)
        except Exception:
            # Fallback to simple print if qi.logging fails
            try:
                fallback_msg = msg % args if args else str(msg)
            except:
                fallback_msg = str(msg) + " " + " ".join(str(arg) for arg in args)
            print("VERBOSE [%s]: %s" % (_get_category(), fallback_msg))

def debug(msg, *args):
    """Logs a message with level DEBUG - shows when level is DEBUG or higher (but not VERBOSE)."""
    # Only log if current level is DEBUG or higher, but NOT VERBOSE
    if _current_log_level >= DEBUG and _current_log_level != VERBOSE:
        try:
            formatted_msg = _format_message(msg, *args)
            # Map debug to qi.logging.verbose since qi doesn't have debug level
            qi.logging.verbose(_get_category(), formatted_msg)
        except Exception:
            # Fallback to simple print if qi.logging fails
            try:
                fallback_msg = msg % args if args else str(msg)
            except:
                fallback_msg = str(msg) + " " + " ".join(str(arg) for arg in args)
            print("DEBUG [%s]: %s" % (_get_category(), fallback_msg))