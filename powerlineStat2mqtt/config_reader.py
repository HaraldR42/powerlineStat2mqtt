import yaml

from .globals import logger, deamon_opts


###################################################################################################################
#
# Parsing YAML config files
#

class ConfigYaml:

    def __init__(self, yaml_file) -> None:
        self.config_error_count = 0    
        try:
            yaml_file.seek(0)
            yaml_dict = yaml.safe_load(yaml_file)
        except Exception as e:
            logger.error( f'Config error ({yaml_file}): {e}')
            self.config_error_count += 1
            return

        if 'Daemon' not in yaml_dict:
            return
        daemon_part = yaml_dict['Daemon']

        for key in daemon_part:
            if key not in deamon_opts:
                logger.error( f'Unknown yaml daemon option "{key}"')
                self.config_error_count += 1
                continue
            deamon_opts[key] = daemon_part[key]
