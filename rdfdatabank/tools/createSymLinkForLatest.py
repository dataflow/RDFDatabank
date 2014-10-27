import os, errno

def get_latest_in_dir(items_list, dirname, fnames):
    # Get list of dir paths pointing to the latest version number and to __latest
    for fname in fnames:
        a = os.path.join(dirname,fname)
        if fname == 'obj':
            dirs = os.listdir(a)
            versions = [int(x.strip('__')) for x in dirs if x.strip('__').isdigit()]
            latestVersion = max(versions)
            b = os.path.join(a, '__%d'%latestVersion)
            c = os.path.join(a, '__latest')
            if not (b, c) in items_list:
                items_list.append((b, c))
    return

def create_latest_symlink(src_dir):
    # Create sym links with the full path
    links_list = []
    os.path.walk(src_dir,get_latest_in_dir,links_list)
    for a, b in links_list:
        try:
            os.symlink(a, b)
        except OSError, e:
            if e.errno == errno.EEXIST:
                os.remove(b)
                os.symlink(a, b)
    return

def get_latest_in_dir2(items_list, dirname, fnames):
    # Get list of dir paths pointing to the parent directory (obj) and the latest version number
    for fname in fnames:
        a = os.path.join(dirname,fname)
        if fname == 'obj':
            dirs = os.listdir(a)
            versions = [int(x.strip('__')) for x in dirs if x.strip('__').isdigit()]
            latestVersion = max(versions)
            b = '__%d'%latestVersion
            if not (a, b) in items_list:
                items_list.append((a, b))
    return

def create_latest_symlink2(src_dir):
    # Create sym links with the relative path
    links_list = []
    os.path.walk(src_dir,get_latest_in_dir2,links_list)   
    for a, b in links_list:
        os.chdir(a)
        try:
            os.symlink(b, '__latest')
        except OSError, e:
            if e.errno == errno.EEXIST:
                os.remove('__latest')
                os.symlink(b, '__latest')
    return
