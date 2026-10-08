import logging

LOGGING_FILE ='/var/log/argoneon.log'
FORMAT_STRING='%(asctime)s %(process)d [%(levelname)s] %(message)s'
DATE_FORMAT='%b %d %y %H:%M:%S'
#
#
#
def enableLogging( enableDebug : bool = False ):
    """
    Configure logging to LOGGING_FILE. Enables DEBUG level if enableDebug is True,
    otherwise INFO level.
    """
    if enableDebug:
        logging.basicConfig( filename=LOGGING_FILE,
                             filemode='a',
                             level=logging.DEBUG,
                             format=FORMAT_STRING,
                             datefmt=DATE_FORMAT)
    else:
        logging.basicConfig( filename=LOGGING_FILE,
                             filemode='a',
                             level=logging.INFO,
                             format=FORMAT_STRING,
                             datefmt=DATE_FORMAT)

#
#
#
def logDebug( message ):
    """Log a DEBUG-level message."""
    logging.debug( message )

#
#
#
def logInfo( message ):
    """Log an INFO-level message."""
    logging.info( message )

#
#
#
def logWarning( message ):
    """Log a WARNING-level message."""
    logging.warning( message )

#
#
#
def logError( message ):
    """Log an ERROR-level message."""
    logging.error( message )

