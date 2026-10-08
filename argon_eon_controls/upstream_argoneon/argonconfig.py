#
# Configuration processing code
#
import os
import configparser
CONFIG_FILE='/etc/argoneon.conf'

#
def setOLEDDefaults(config):
    """
    Setup the default settings for the OLED section of the config file. Fills in
    missing keys with defaults: screenduration, screensaver, screenlist, and enabled.
    """
    if not 'OLED' in config.keys():
        config['OLED'] = {}

    if not 'screenduration' in config['OLED'].keys():
        config['OLED']['screenduration'] = '40';
    if not 'screensaver' in config['OLED'].keys():
        config['OLED']['screensaver'] = '30'
    if not 'screenlist' in config['OLED'].keys():
        config['OLED']['screenlist'] = 'clock cpu storage bandwidth raid ram temp ip'
    if not 'enabled' in config['OLED'].keys():
        config['OLED']['enabled'] = 'Y'

#
def setGeneralDefaults(config):
    """
    Setup the defaults for the General section of the configuration file.
    """
    if not 'General' in config.keys():
        config['General'] = {'temperature' : 'C'}

    if not 'temperature' in  config['General'].keys():
        config['General']['temperature'] = 'C';

    if not 'debug' in config['General'].keys():
        config['General']['debug'] = 'N'

#
def loadConfigAndDefaults():
    """
    Load up the configuration file.  We utilize a single config file, and for everything that is
    missing we setup default values for it.  This allows for one stop shopping for setting up the
    configuration file, and if we need to we could actually write out the config if the file does 
    not exist.
    """

    try:
        config = configparser.ConfigParser()
        config.read( CONFIG_FILE )
    except Exception as e:
        logError( "Error processing configuration file " + CONFIG_FILE + "exception is " + e )

    #
    # Setup defaults for anything that is missing
    #
    setGeneralDefaults( config )
    setOLEDDefaults( config )
    if not 'CPUFan' in config.keys():
        config['CPUFan'] = {'55.0':'30', '60.0':'55', '65.0':'100'}
    if not 'HDDFan' in config.keys():
        config['HDDFan'] = {'40.0':'25', '44.0':'30', '46.0':'35',
                            '48.0':'40', '50.0':'45', '50.0':'50',
                            '52.0':'55', '54.0':'60', '60.0':'100'}
 
    if not os.path.exists( CONFIG_FILE ):
        with open( CONFIG_FILE, 'w' ) as configfile:
            config.write(configfile)

    return config

#
def loadCPUFanConfig():
    """
    Load the main configuration and return just the CPUFan portion. Configuration is
    reloaded on every call so that changes to the config file are picked up automatically.
    """
    return loadConfigAndDefaults()['CPUFan']

#
def loadHDDFanConfig():
    """
    Load the main configuration and return just the HDDFan portion. Configuration is
    reloaded on every call so that changes to the config file are picked up automatically.
    """
    return loadConfigAndDefaults()['HDDFan']

#
def loadOLEDConfig():
    """
    Obtain the OLED configuration info, and return it.
    """
    config = loadConfigAndDefaults()['OLED']
    return config;

#
def loadTempConfig():
    """
    Return the value we are supposed to be using for temperature, either Celcius, or Fahrenheit.
    """
    return loadConfigAndDefaults()['General']['temperature']

#
def loadDebugMode():
    """
    Return the value of the debugging setting.  'Y' is used to enable debug, Anything else is
    no debugging
    """
    if loadConfigAndDefaults()['General']['debug'] == 'Y':
        return True
    return False
