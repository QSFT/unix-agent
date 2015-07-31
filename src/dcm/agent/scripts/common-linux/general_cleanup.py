import os
import sys
import logging

_g_logger = logging.getLogger(__name__)


def main(bin_path, dcm_basedir, dbfile):
    dirs_to_clean = [os.path.join(dcm_basedir, 'logs'),
                     os.path.join(dcm_basedir, 'secure')]

    for clean_dir in dirs_to_clean:
        for (dirpath, dirname, filenames) in os.walk(clean_dir):
            for file in filenames:
                if not os.path.join(dirpath, file) == dbfile:
                    cmd = '%s %s' % \
                        (os.path.join(bin_path, 'secureDelete'),
                         os.path.join(dirpath, file))
                    os.system(cmd)

    files_to_clean = ["/var/lib/waagent/provisioned"]
    for f in files_to_clean:
        try:
            os.remove(f)
        except OSError as osEx:
            # in many cases the file will not be there
            if osEx.errno != 2:
                sys.stderr.write(str(osEx))


if __name__ == "__main__":
    try:
        dcm_basedir = os.environ.get('DCM_BASEDIR')
        dbfile = sys.argv[1]
    except Exception as ex:
        _g_logger.exception("general_cleanup failed: " + str(ex))
        sys.exit(1)
    bin_path = os.path.dirname(os.path.abspath(__file__))
    main(bin_path, dcm_basedir, dbfile)