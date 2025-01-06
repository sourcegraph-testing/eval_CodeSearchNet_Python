import jinja2 as _jj
import tempfile as _tempfile
import os as _os
import datetime as _dt
import shutil as _shutil

basedir = '/u1/facet/physics/logbook/data'


# ============================
# Copy files as needed
# ============================
def _copy_file(filepath, fulltime):
    if filepath is None:
        filepath_out = ''
    else:
        filename  = _os.path.basename(filepath)
        root, ext = _os.path.splitext(filename)
        filepath_out = fulltime + ext
        copypath = _os.path.join(basedir, filepath_out)
        _shutil.copyfile(filepath, copypath)

    return filepath_out


def print2elog(author='', title='', text='', link=None, file=None, now=None):
    """
    Prints to the elog.
    
    Parameters
    ----------

    author : str, optional
        Author of the elog.
    title : str, optional
        Title of the elog.
    link : str, optional
        Path to a thumbnail.
    file : str, optional
        Path to a file.
    now : :class:`datetime.datetime`
        Time of the elog.
    """
    # ============================
    # Get current time
    # ============================
    if now is None:
        now  = _dt.datetime.now()
    fulltime = now.strftime('%Y-%m-%dT%H:%M:%S-00')

    # ============================
    # Copy files
    # ============================
    if not ((link is None) ^ (file is None)):
        link_copied = _copy_file(link, fulltime)
        file_copied = _copy_file(file, fulltime)
    else:
        raise ValueError('Need both file and its thumbnail!')

    # ============================
    # Jinja templating
    # ============================
    loader = _jj.PackageLoader('pytools.facettools', 'resources/templates')
    env = _jj.Environment(loader=loader, trim_blocks=True)
    template = env.get_template('facetelog.xml')
    stream = template.stream(author=author, title=title, text=text, link=link_copied, file=file_copied, now=now)

    # ============================
    # Write xml
    # ============================
    with _tempfile.TemporaryDirectory() as dirname:
        filename = '{}.xml'.format(fulltime)
        filepath = _os.path.join(dirname, filename)

        with open(filepath, 'w+') as fid:
            # stream.disable_buffering()
            stream.dump(fid)

        finalpath = _os.path.join(basedir, filename)
        # _shutil.copyfile(filepath, 'new.xml')
        _shutil.copyfile(filepath, finalpath)
