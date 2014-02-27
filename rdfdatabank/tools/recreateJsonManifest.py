"""
Recreate __manifest.json for a data packages, based on files on disk (version-mismatch.log)
The list of uuids are read from a csv file of the format uuid, currentversion
In here, the silo is assumed to digital.bodleian
"""
from unicodeCSV import UnicodeReader
import os
import shutil
import codecs
import json
import uuid
import stat

def pairtree_path(seq, length):
    a = [seq[i:i+length] for i in range(0, len(seq), length)]
    return "/".join(a)

fname = "version-mismatch2.log"
csvfo = file(fname, 'r')

ur = UnicodeReader(csvfo)
heading=ur.next()
data = ur.next()

while data:
    pid = data[0]
    version = data[1]
    uuid_path = pairtree_path(pid, 2)
    path = '/silos/digital.bodleian/pairtree_root/%s/obj/'%uuid_path
    print pid
    print version
    print path
    manifest = {}
    manifest["metadata"] = {"uuid": uuid.UUID(pid).hex, "embargoed": False, "embargoed_until": "", "createdby": "databankClient"}
    manifest["rdffileformat"] = "xml"
    manifest["item_id"] = pid
    manifest["currentversion"] = version
    manifest["versions"] = [str(x) for x in range(int(version)+1)]
    manifest["rdffilename"] = "manifest.rdf"
    manifest["metadata_files"] = {}
    manifest["subdir"] = {}
    manifest["files"] = {}
    manifest["versionlog"] = {}
    for x in range(int(version)+1):
        manifest["metadata_files"][str(x)] = []
        manifest["subdir"][str(x)] = []
        manifest["files"][str(x)] = []
        manifest["versionlog"][str(x)] = []
    manifest["version_dates"] = {}
    filesAdded = []
    for x in range(int(version)+1):
        fileAdded = False
        for f in os.listdir(os.path.join(path, '__%d'%x)):
            if os.path.isdir(os.path.join(path, '__%d'%x, f)):
                manifest["subdir"][str(x)].append(f)
            elif f.startswith('3='):
                manifest["version_dates"][str(x)] = f.replace('3=', '').replace(',', '.').replace('+',':')
            elif not f.startswith('4='):
                manifest["files"][str(x)].append(f)
                if not f == "manifest.rdf" and not f in filesAdded:
                     fileAdded = f
                     filesAdded.append(f)
        if x == 0:
            manifest["versionlog"][str(x)].append("Created new data package")
        elif fileAdded:
            manifest["versionlog"][str(x)].append("Version number incremented from %d to %d"%(x-1, x))
            manifest["versionlog"][str(x)].append("Added or updated file %s"%fileAdded)
        else:
            manifest["versionlog"][str(x)].append("Version number incremented from %d to %d"%(x-1, x))
            manifest["versionlog"][str(x)].append("Updated file manifest.rdf")
    manifest["date"] = manifest["version_dates"][version]
    manf = os.path.join(path, '__manifest.json')
    fo = open(manf, 'w')
    fo.write(json.dumps(manifest))
    fo.close()
    #info = os.stat(path)
    #os.fchown(manf, info[stat.ST_UID], info[stat.ST_GID])
    #os.fchown(manf, 33, 33)
    #shutil.chown(manf, 'www-data', 'www-data')
    try:
        data = ur.next()
    except:
        data = None
    print ''
csvfo.close()
