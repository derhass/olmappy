#!/usr/bin/python3

# required libraries

import enum
import json
import os
import stat
import time
import urllib
import urllib3

# configuration

urlBase = 'https://overloadmaps.com'
urlPath = '/data/'
urlMapsAll = 'all.json'

mapDir = '/home/mh/tmp/DONTBACKUP/olmappy/'



# error types 

class OlmappyError(Exception):
    pass

class OlmappyTransferError(OlmappyError):
    def __init__(self, message):
        self.message = message

class OlmappyParseError(OlmappyError):
    def __init__(self, message):
        self.message = message

class OlmappyJSONWriteError(OlmappyError):
    def __init__(self, message):
        self.message = message

class OlmappyValidationError(OlmappyError):
    def __init__(self, message):
        self.message = message

class OlmappyUpdateError(OlmappyError):
    def __init__(self, message):
        self.message = message

# log functions

class LogLevel(enum.IntEnum):
    ERROR = 0
    WARN = 1
    INFO = 2
    DEBUG = 3

logLevel = LogLevel.DEBUG

def Log(message, level=LogLevel.INFO):
    if (level <= logLevel):
        print(message)

def Error(message):
    Log(message, LogLevel.ERROR)

def Warn(message):
    Log(message, LogLevel.WARN)

def Info(message):
    Log(message, LogLevel.INFO)

def Debug(message):
    Log(message, LogLevel.DEBUG)

# helper function for maps
def mapName(m):
    return '"' + m['id'] + '/' + m['filename'] + '"'

# class for managing the locally stored maps
class localMapManager:
    def __init__(self):
        self.maps = []
        self.mapDir = mapDir
        self.hiddenDir = 'hidden/'
        self.replaceDir = 'replaced/'
        os.makedirs(self.mapDir, exist_ok=True)
        os.makedirs(self.mapDir + self.hiddenDir, exist_ok=True)
        os.makedirs(self.mapDir + self.replaceDir, exist_ok=True)
        self.loadMapList()
        self.validateMapList()

    def getMapListFileName(self):
        return self.mapDir + 'olmappy.json'

    def loadMapList(self):
        filename = self.getMapListFileName()
        try:
            indexFile = open(file = filename, mode = 'rt', encoding = 'utf-8')
            try:
                self.maps = json.load(indexFile)
                Info('read json map list ' + filename + ': ' + str(len(self.maps)) + ' entries')
            except Exception as E:
                raise OlmappyParseError('json map list file ' + filename + ' could not be parsed: ' + str(E)) from E
        except OlmappyError as E:
            Warn('json map list ' + filename + ' was corrupted: ' + str(E))
            self.maps = []
        except Exception as E:
            Warn('json map list ' + filename + ' could not be read: ' + str(E))
            self.maps = []

    def saveMapList(self):
        filename = self.getMapListFileName()
        try:
            indexFile = open(file = filename, mode = 'wt', encoding = 'utf-8')
            try:
                json.dump(self.maps, indexFile)
                Info('wrote json map list ' + filename + ': ' + str(len(self.maps)) + ' entries')
            except Exception as E:
                raise OlmappyJSONWriteError('failed to dump map list to json file ' + filename + ': ' + str(E)) from E
        except Exception as E:
                Warn('json map list ' + filename + ' could not be written: ' + str(E))

    def findMapById(self, mapId):
        for m in self.maps:
            if m['id'] == mapId:
                return m
        return None

    def findMapByFileName(self, mapFileName):
        for m in self.maps:
            if m['filename'] == mapFileName:
                return m
        return None

    def compareMaps(self, a, b):
        if a['mtime'] != b['mtime']:
            Debug('maps ' + mapName(a) + ' and ' + mapName(b) + ' differ in mtime')
            return False
        if a['levels'] != b['levels']:
            Debug('maps ' + mapName(a) + ' and ' + mapName(b) + ' differ in levels specification')
            return False
        if (a['size'] != b['size']) or a['size'] < 1 or b['size'] < 1:
            Debug('maps ' + mapName(a) + ' and ' + mapName(b) + ' differ in size')
            return False
        return True

    def replaceMap(self, m):
        try: 
            d = self.mapDir + self.replaceDir
            a = self.GetMapFilename()
            b = d + m['filename'] + '_replaced_' + m['id']
            os.replace(a,b)
            Warn('backed up "' + a + '" to "' + b + '"') 
        except Exception as E:
            Warn('Failed to back up replaced map ' + mapName(m) + ': ' + str(E))
        self.maps.remove(m)

    def findExistingMap(self, m):
        myMapId = self.findMapById(m['id'])
        myMapFile = self.findMapByFileName(m['filename'])
        if myMapId == None and myMapFile == None:
            return None
        elif myMapId == myMapFile:
            return myMapId
        else:
            replaceMap = myMapId
            if myMapId == None:
                replaceMap = myMapFile
            Warn('found REPLACED map: ' + mapName(m) + ' conflicting with existing map ' + mapName(replaceMap))
            self.replaceMap(replaceMap)
            return None

    def GetMapFilename(self, m):
        d = self.mapDir
        if m['hidden'] > 0:
            d = d + self.hiddenDir
        return d + m['filename']

    def validateMap(self, m):
        try:
            if 'filename_encoded' not in m:
                raise OlmappyValidationError('FILENAME part missing')
            if 'filename' not in m:
                raise OlmappyValidationError('FILENAME (decoded) part missing')
            if 'size' not in m:
                raise OlmappyValidationError('SIZE part missing')
            if 'mtime' not in m:
                raise OlmappyValidationError('MTIME part missing')
            if 'levels' not in m:
                raise OlmappyValidationError('LEVELS part missing')
            if 'id' not in m:
                raise OlmappyValidationError('ID part missing')
            if 'hidden' not in m:
                m['hidden'] = 0

            filename = self.GetMapFilename(m)
            fsize = os.stat(filename).st_size
            if fsize != m['size']:
                raise OlmappyValidationError('file size differs, expected: '+str(m['size']) + ', got: ' + str(fsize))

        except Exception as E:
            Warn('Failed to validate map ' + str(m) + ': ' + str(E))
            return False
        return True

    def validateMapList(self):
        numEntries = len(self.maps)
        numValidated = 0
        mapsValidated = []
        Debug('local map list: validating ' + str(numEntries) + ' entries')
        for m in self.maps:
            if self.validateMap(m):
                mapsValidated = mapsValidated + [m]
                numValidated = numValidated + 1
        Debug('local map list: validated ' + str(numValidated) + ' out of ' + str(numEntries) + ' entries')
        if (numValidated < numEntries) :
            Warn('local map list: ' + str(numEntries - numValidated) + ' entries were not correct')
        self.maps = []
        for m in mapsValidated:
            myMap = self.findExistingMap(m)
            if myMap == None:
                self.maps = self.maps + [m]
            else:
                Warn('map ' + mapName(m) + ' is already present, ignoring it')
                #TODO: check if they differ???
        Debug('local map list: found ' + str(len(self.maps)) + ' unique entries')

    def updateMapFromRemote(self, m, remote):
        myMap = self.findExistingMap(m)
        myMapId = self.findMapById(m['id'])
        myMapFile = self.findMapByFileName(m['filename'])
        doUpdate = False
        code = 0
        if myMap == None:
            Info('found NEW map: ' + mapName(m))
            doUpdate = True
            code = 1
        else:
            Debug('found existing map: ' + mapName(myMap))
            if  self.compareMaps(m, myMap):
                Debug('existing Map is unchanged')
            else:
                m['hidden'] = myMap['hidden']
                self.maps.remove(myMap)
                doUpdate = True
                code = 2
                Info('found UPDATED map: ' + mapName(m))

        if doUpdate:
            filename = self.mapDir + m['filename']
            Info("downloading " + mapName(m) + ' to "' + filename + '"')
            remote.download(m, filename)
            if self.validateMap(m):
                Debug('successfully added map ' + mapName(m))
                self.maps = self.maps + [m]
                return code
            else:
                raise OlmappyUpdateError('downloaded map could not be validated')

        return 0         

    def updateFromRemote(self, remote):
        cntNew = 0
        cntUp = 0
        cntFail = 0
        res = False
        try:
            if not remote.update():
                raise OlmappyUpdateError('remote map list could not be updated')
            for m in remote.maps:
                try:
                    code = self.updateMapFromRemote(m, remote)
                    if code > 0:
                        try:
                            self.saveMapList()
                        except Exception as E:
                            Warn('map list could not be saved: ' + str(E))
                        if code == 1:
                            cntNew = cntNew + 1
                        else:
                            cntUp = cntUp + 1
                except Exception as E:
                    Warn('remote map ' + mapName(m) + ' could not be updated: ' + str(E))
                    cntFail = cntFail + 1

            res = True
        except Exception as E:
            res = False
        Info('UPDATE: ' + str(cntNew) + 'new, ' + str(cntUp) + ' updated, ' + str(cntFail) + ' failed')
        return res

    def importDirFromRemote(self, d, remote, hidden=0):
        remote.update()
        for fname in os.listdir(d):
            fullname = d + fname
            try:
                fname2 = fname # TODO: hidden file name part removal
                if stat.S_ISREG(os.lstat(fullname).st_mode):
                    m = self.findMapByFileName(fname2)
                    if m == None:
                        Debug('import: file "' + fullname + '" not yet known')
                        # TODO: what if file name is not unique?
                        newMap = remote.findMapByFileName(fname2)
                        if newMap == None:
                            Warn('import: file "' + fullname + '" not on remote map list')
                        else:
                            newMap['hidden'] = hidden
                            if self.validateMap(newMap):
                                self.maps = self.maps + [newMap]
                                Info('import: file "' + fullname + '" imported')
                            else:
                                Warn('import: file "' + fullname + '" did not match info from server')

                    else:
                        Debug('import: file "' + fullname + '" already in index')
                else:
                    Debug('import: ignoring non-file ' + fullname)
            except Exception as E:
                Warn('import: failed to import "'+fullname+'": ' + str(E))

    def importFromRemote(self, remote):
        self.importDirFromRemote(self.mapDir, remote)
        

        
# class for managing the remote map server

class remoteMapManager:
    def __init__(self):
        self.maps = []
        self.valid = False
        self.urlBase = urlBase
        self.urlMapPath = urlPath
        self.urlMaps = urlMapsAll

    def getMapList(self):
        url = self.urlBase + self.urlMapPath + self.urlMaps
        try:
            request = urllib3.PoolManager().request('GET', url)
            if (request.status >= 200 and request.status < 300):
                try:
                    Debug('querying remote map list ' + url)
                    self.maps = json.loads(request.data.decode('utf-8'))
                    self.valid = True
                    Info('retrieved remote map list ' + url + ': ' + str(len(self.maps)) + ' entries')
                except Exception as E:
                    raise OlmappyParseError('remote json map list ' + url + ' could not be parsed: ' + str(E)) from E
            else:
                raise OlmappyTransferError('retrieving map list ' + url + ' failed with status code ' + str(request.status))
        except OlmappyError as E:
            self.maps = []
            self.valid = False
            raise E
        except Exception as E:
            self.maps = []
            self.valid = False
            raise OlmappyTransferError('failed to GET map list ' + url) from E

    def validateMap(self, m):
        try:
            if 'url' in m:
                url = m['url']
                if len(url) < 6:
                    raise OlmappyValidationError('malformed URL: too short, excect at least /i/a.b')
                if url[0] == '/':
                    parts = url.split('/')
                    if len(parts) < 2:
                        raise OlmappyValidationError('malformed URL: expected at least 2 parts: id/filename')
                    m['id'] = parts[-2]
                    m['filename_encoded'] = parts[-1]
                    if len(m['id']) < 1:
                        raise OlmappyValidationError('malformed URL: empty ID part in id/filename')
                    if len(m['filename_encoded']) < 1:
                        raise OlmappyValidationError('malformed URL: empty FILENAME part in id/filename')
                    m['filename'] = urllib.parse.unquote(m['filename_encoded'])
                    if len(m['filename']) < 1:
                        raise OlmappyValidationError('malformed URL: urldecoded FILENAME part was empty')
                else:
                    raise OlmappyValidationError('malformed URL: does not start with /')
            else:
                raise OlmappyValidationError('missing URL')
            if 'mtime' not in m:
                Warn('remote map ' + mapName(m) + ' has missing mtime, faking it')
                m['mtime'] = time.time()
            if 'size' in m:
                if m['size'] < 1:
                    raise OlmappyValidationError('invalid map size: ' + str(m['size']))
            else:
                Warn('remote map ' + mapName(m) + ' has missing size')
                m['size'] = -1 # will later be updated after download
            if 'levels' not in m:
                raise OlmappyValidationError('LEVELS part missing')
            m['hidden'] = 0

        except Exception as E:
            Warn('failed to validate remote map ' +str(m) + ': ' + str(E))
            return False
        return True

    def validateMapList(self):
        if not self.valid:
            Warn('remote map list is not in VALID state')
            return False
        numEntries = len(self.maps)
        numValidated = 0
        mapsValidated = []
        Debug('remote map list: validating ' + str(numEntries) + ' entries')
        for m in self.maps:
            if self.validateMap(m):
                mapsValidated = mapsValidated + [m]
                numValidated = numValidated + 1
        Debug('remote map list: validated ' + str(numValidated) + ' out of ' + str(numEntries) + ' entries')
        if (numValidated < numEntries) :
            Warn('remote map list: ' + str(numEntries - numValidated) + ' entries were not correct')
        self.maps = mapsValidated
        if (numValidated < 1):
            Warn('remote map list: no valid entries found')
            self.valid = False
        return self.valid

    def findMapByFileName(self, mapFileName):
        for m in self.maps:
            if m['filename'] == mapFileName:
                return m
        return None
        
    def update(self, forceRefresh = False):
        if forceRefresh:
            self.vaild = False
        try:
            if not self.valid:
                self.getMapList()
                self.validateMapList()
        except Exception as E:
            Warn('remote map list update failed: ' + str(E))
            self.valid = False
        return self.valid

    def download(self, m, outFileName):
        try:
            url = self.urlBase +  m['url']
            outFile = open(outFileName, 'wb')
            Debug('attempting to download ' + url)
            request = urllib3.PoolManager().request('GET', url, preload_content = False)
            for chunk in request.stream(64*1024):
                outFile.write(chunk)
            outFile.flush()
            if m['size'] < 0:
                m['size'] = outFile.tell()
                Warn('assuming retrieved file size for ' + url + ' is correct: ' +str(m['size']))
            outFile.close()
        except Exception as E:
            text = 'failed to download ' + url + ' to "' + outFileName + '": ' + str(E)
            Warn(text)
            raise OlmappyTransferError(text) from E


#print(getMapList())
m = localMapManager()
r = remoteMapManager()
m.importFromRemote(r)
m.updateFromRemote(r)
m.saveMapList()

