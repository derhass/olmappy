#!/usr/bin/python3

# required libraries

import argparse
import enum
import filecmp
import json
import os
import stat
import time
import urllib
import urllib3

##############################################################################
# internally used Exception types                                            #
##############################################################################

class OlmappyError(Exception):
    def __init__(self, message):
        self.message = message

class OlmappyConfigError(OlmappyError):
    pass

class OlmappyTransferError(OlmappyError):
    pass

class OlmappyParseError(OlmappyError):
    pass

class OlmappyJSONWriteError(OlmappyError):
    pass

class OlmappyValidationError(OlmappyError):
    pass

class OlmappyUpdateError(OlmappyError):
    pass

##############################################################################
# Logging functions                                                          #
##############################################################################

class LogLevel(enum.IntEnum):
    ERROR = 0
    WARN = 1
    INFO = 2
    DEBUG = 3

def Log(message, level=LogLevel.INFO):
    if (level <= Config.settings['logLevel']):
        print(str(level) + ': ' + message)

def Error(message):
    Log(message, LogLevel.ERROR)

def Warn(message):
    Log(message, LogLevel.WARN)

def Info(message):
    Log(message, LogLevel.INFO)

def Debug(message):
    Log(message, LogLevel.DEBUG)

##############################################################################
# Level properties                                                           #
##############################################################################

class MapType(enum.IntEnum):
    SinglePlayer = 1
    ChallengeMode = 2
    MultiPlayer = 4

    def getDesc(self):
        v = self.value
        if v == self.SinglePlayer:
            return 'SP'
        elif v == self.ChallengeMode:
            return 'CM'
        elif v == self.MultiPlayer:
            return 'MP'
        return 'UN'

    @classmethod
    def getCombinedDesc(cls, v, fillOthers = '  ', sep=','):
        desc = '['
        cnt = 0
        for m in list(cls):
            if m & v:
                if cnt > 0:
                    desc = desc + sep
                desc = desc + m.getDesc()
                cnt = cnt + 1
            else:
                if fillOthers != None:
                    if cnt > 0:
                        desc = desc + sep
                    desc = desc + fillOthers
                    cnt = cnt + 1
        desc = desc + ']'
        return desc

    @classmethod
    def MapTypeString(cls, desc):
        t = desc.casefold()
        for m in list(cls):
            d = m.getDesc().casefold()
            if d == t:
                return m
        raise ValueError('Map type ' +desc + ' can\'t be parsed')

##############################################################################
# utility functions                                                          #
##############################################################################

def stringAsBool(s):
    s2 = s.strip().casefold()
    if s2 in ['true', 'on', 'yes', '1', 'enable', 'enabled']:
        return True
    if s2 in ['false', 'off', 'no', '0', 'disable', 'disabled']:
        return False
    raise ValueError('cant parse boolean value from ' + s)

def equalFileNames(a, b):
    if Config.settings['filenameCaseSensitive']:
        return (a.casefold() == b.casefold())
    else:
        return (a == b)

def mapStatus(m):
    desc = '(' + (' ' if m['hidden'] > 0 else '*') + ')'
    return desc

def mapTypes(m, compact=False):
    return MapType.getCombinedDesc(m['types'], None if compact else '  ')

def mapAndLevelName(m):
    desc = '"' + m['filename'] + '": ['
    cnt = 0
    for n in m['names']:
        if cnt > 0:
            desc = desc + ', '
        desc = desc + '"' + n + '"'
        cnt = cnt + 1
    desc = desc + ']'
    return desc

def mapName(m):
    #return '"' + m['id'] + '/' + m['filename'] + '"'
    return mapAndLevelName(m) + ' ' + mapTypes(m, True)

def mapTime(m):
    t = time.localtime(m['mtime'])
    return time.strftime('%Y-%m-%d %H:%M:%S', t)

def mapDesc(m):
    desc = mapTypes(m) + ' ' + mapStatus(m) + ' ' +  mapAndLevelName(m)
    desc = desc + ' (' + mapTime(m) + ')'
    return desc

def parseDateTime(s):
    try:
        err = None
        formats = ['%Y-%m-%d %H:%M:%S',
                   '%Y-%m-%d_%H:%M:%S',
                   '%Y-%m-%d %H:%M',
                   '%Y-%m-%d_%H:%M',
                   '%m/%d/%Y %h:%m:%s %p',
                   '%m/%d/%Y %h:%m %p',
                   '%m/%d/%Y %h %m %s %p',
                   '%m/%d/%Y %h %m %p',
                   '%Y-%m-%d',
                   '%m/%d/%Y',
                   '%c']
        for f in formats:
            try:
                t = time.strptime(s, f)
                return time.mktime(t)
            except ValueError as E:
                err = E
        raise err
    except Exception as E:
        raise ValueError from E

##############################################################################
# base class for the map managers                                            #
##############################################################################

class MapManager:
    def __init__(self):
        self.maps = []
        self.valid = False
        self.name = 'generic'
        self.timestamp = time.time();

    def findMapById(self, mapId):
        for m in self.maps:
            if m['id'] == mapId:
                return m
        return None

    def findMapByURL(self, mapUrl):
        for m in self.maps:
            if m['url'] == mapUrl:
                return m
        return None

    @staticmethod
    def RemoveFilenameDecoration(filename):
        idxLast = filename.rfind('_')
        if idxLast < 1:
            return None
        if filename[idxLast:] == '_hidden' or filename[idxLast:] == '_replaced':
            name = filename[0:idxLast]
            idxDot = name.rfind('.')
            idxId = name.rfind('_')
            if idxDot < 1:
                return None
            if idxId > idxDot:
                return name[0:idxId]
            return name
        else:
            return None

        f = m['filename']
        if replaced:
            f = f + '_' + m['id'] + '_replaced'
        elif hidden:
            f = f + '_' + m['id'] + '_hidden'
        return f

    @staticmethod
    def GetMapFilenameAs(m, hidden=False, replaced = False):
        f = m['filename']
        if replaced:
            f = f + '_' + m['id'] + '_replaced'
        elif hidden:
            f = f + '_' + m['id'] + '_hidden'
        return f

    def findMapByFileName(self, mapFileName):
        for m in self.maps:
            if equalFileNames(m['filename'], mapFileName):
                return m
        return None

    def findMapByHiddenFileName(self, mapFileName):
        for m in self.maps:
            if equalFileNames(self.GetMapFilenameAs(m, hidden=True), mapFileName):
                return m
        return None

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
                Warn(self.name + ' map ' + mapName(m) + ' has missing mtime, faking it')
                m['mtime'] = self.timestamp
            if 'size' in m:
                if m['size'] < 1:
                    raise OlmappyValidationError('invalid map size: ' + str(m['size']))
            else:
                Warn(self.name + ' map ' + mapName(m) + ' has missing size')
                m['size'] = -1 # will later be updated after download
            if 'levels' not in m:
                raise OlmappyValidationError('LEVELS part missing')
            else:
                if len(m['levels']) < 1:
                    raise OlmappyValidationError('LEVELS part empty')
                m['names'] = []
                for l in m['levels']:
                    if 'type' not in l:
                        raise OlmappyValidationError('LEVEL without a type')
                    if 'name' not in l:
                        raise OlmappyValidationError('LEVEL without a name')
                    mt = MapType.MapTypeString(l['type'])
                    if 'types' not in m:
                        m['types'] = mt
                    else:
                        m['types'] = m['types'] | mt
                    if l['name'] not in m['names']:
                        m['names'] = m['names'] + [l['name']]
            if 'hidden' not in m:
                m['hidden'] = 0

        except Exception as E:
            Warn('failed to validate ' +self.name + ' map ' +str(m) + ': ' + str(E))
            return False
        return True

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

    @staticmethod
    def writeMapList(filename, mapList):
        try:
            indexFile = open(file = filename, mode = 'wt', encoding = 'utf-8')
            try:
                json.dump(mapList, indexFile, indent=4)
                Debug('wrote json map list ' + filename + ': ' + str(len(mapList)) + ' entries')
            except Exception as E:
                raise OlmappyJSONWriteError('failed to write map list to json file ' + filename + ': ' + str(E)) from E
        except Exception as E:
                Warn('json map list ' + filename + ' could not be written: ' + str(E))

    def listMaps(self, doExport=False):
        name = 'EXPORTLIST' if doExport else 'LIST'
        cntListed = 0
        cntFiltered = 0
        exported = []
        for m in self.maps:
            if not Filter.apply(m):
                cntFiltered = cntFiltered + 1
                continue
            if doExport:
                exported = exported + [m]
            else:
                print(mapDesc(m))
            cntListed = cntListed + 1
        if doExport:
            self.writeMapList(Cmd.args.export_file[0], exported)

        if doExport:
           Info(name + ': ' + str(cntListed) + ' exported, ' + str(cntFiltered) + ' not exported')
        else:
           Debug(name + ': ' + str(cntListed) + ' found, ' + str(cntFiltered) + ' filtered')

##############################################################################
# class for managing the locally stored maps                                 #
##############################################################################

class localMapManager(MapManager):
    def __init__(self):
        MapManager.__init__(self)
        self.name = 'local'
        self.indexName = 'olmappyIndex.json'
        self.hiddenDir = 'hidden/'
        self.replaceDir = 'replaced/'
        self.mapDir = './'

    def update(self, forceRefresh = False):
        if self.mapDir != Config.settings['mapPath']:
            self.mapDir = Config.settings['mapPath']
            forceRefresh = True
        if forceRefresh or not self.valid:
            os.makedirs(self.mapDir, exist_ok=True)
            os.makedirs(self.mapDir + self.hiddenDir, exist_ok=True)
            os.makedirs(self.mapDir + self.replaceDir, exist_ok=True)
            self.loadMapList()
            self.validateMapList()

    def getMapListFileName(self):
        return self.mapDir + self.indexName

    @staticmethod
    def loadMapListFile(filename, valid=False):
        try:
            indexFile = open(file = filename, mode = 'rt', encoding = 'utf-8')
            try:
                mapList = json.load(indexFile)
                valid = True
                Debug('read json map list ' + filename + ': ' + str(len(mapList)) + ' entries')
            except Exception as E:
                raise OlmappyParseError('json map list file ' + filename + ' could not be parsed: ' + str(E)) from E
        except OlmappyError as E:
            Warn('json map list ' + filename + ' was corrupted: ' + str(E))
            mapList = []
            valid = True
        except Exception as E:
            Warn('json map list ' + filename + ' could not be read: ' + str(E))
            mapList = []
            valid = True
        return mapList, valid

    def loadMapList(self):
        filename = self.getMapListFileName()
        self.maps , self.valid = self.loadMapListFile(filename, self.valid)

    def saveMapList(self):
        self.writeMapList(self.getMapListFileName(), self.maps)

    def doActualReplace(self, src, dst):
        try:
            Warn('Replace File "' + src + '" to "' + dst + '"')
            target = dst
            index = 1
            while True:
                print('A', target, index)
                if os.path.isfile(target):
                    if filecmp.cmp(src, target, shallow=False):
                        Warn('Target "' + target + '" already exists and is identical, removing source only')
                        os.remove(src)
                        print('B', target, index)
                        break
                    else:
                        newtarget = dst + '_' +str(index)
                        index = index + 1
                        Warn('Target "' + target + '" already exists, retrying with "' + newtarget + '"')
                        target = newtarget
                else:
                    os.rename(src,target)
                    print('C', target, index)
                    break
        except Exception as E:
            Warn('Failed to replace "' + src + '" to "' + dst + '": ' + str(E))
            raise E


    def RenameMap(self, src, dst):
        try:
            os.rename(src,dst)
            Debug('renamed "' + src + '" to "' + dst + '"')
        except Exception as E:
            Warn('Failed to rename "' + src + '" to "' + dst + '": ' + str(E))
            raise E

    def doReplaceFile(self, filename, Id='UNKNOWNID'):
        try: 
            basename = os.path.basename(filename) 
            d = self.mapDir + self.replaceDir
            b = d + basename + '_' + Id + '_replaced'
            self.doActualReplace(filename,b)
        except Exception as E:
            Warn('Failed to back up replaced file "' + filename + '": ' + str(E))

    def doReplaceMap(self, m):
        try: 
            a = self.GetMapPath(m)
            b = self.GetMapPathAs(m, replaced=True)
            self.doActualReplace(a,b)
        except Exception as E:
            Warn('Failed to back up replaced map ' + mapName(m) + ': ' + str(E))

    def findAndReplaceExistingMap(self, m):
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
            Warn('found map: ' + mapName(m) + ' conflicting with existing map ' + mapName(replaceMap)+ ', replacing it')
            self.doReplaceMap(replaceMap)
            self.maps.remove(replaceMap)
            return None

    def GetMapPathAs(self, m, hidden=False, replaced = False):
        d = self.mapDir
        f = self.GetMapFilenameAs(m, hidden, replaced)
        if replaced:
            d = d + self.replaceDir
        elif hidden:
            d = d + self.hiddenDir
        return d + f

    def GetMapPath(self, m):
        return self.GetMapPathAs(m, hidden=( m['hidden'] > 0), replaced = False)

    def validateMap(self, m):
        if not MapManager.validateMap(self, m):
            return False
        try:
            if 'filename_encoded' not in m:
                raise OlmappyValidationError('FILENAME part missing')
            if 'filename' not in m:
                raise OlmappyValidationError('FILENAME (decoded) part missing')
            if 'id' not in m:
                raise OlmappyValidationError('ID part missing')

            filename = self.GetMapPath(m)
            fsize = os.stat(filename).st_size
            if fsize != m['size']:
                raise OlmappyValidationError('file size differs, expected: '+str(m['size']) + ', got: ' + str(fsize))
            if m['hidden'] > 0:
                filename2 = self.GetMapPathAs(m, hidden=False)
            else:
                filename2 = self.GetMapPathAs(m, hidden=True)
            try:
                fsize2 = os.stat(filename2).st_size
                Debug('file "' + filename2 + '" present but should be shadowed by "' + filename +'"')
                if filecmp.cmp(filename, filename2, shallow=False):
                    Info('deleting "' + filename2 + '" as we already have "' + filename + '"')
                    os.remove(filename2)
                else:
                    Warn('replacing "' + filename2 + '" as we already have "' + filename + '" but files are NOT identical')
                    self.doReplaceFile(filename2)
            except FileNotFoundError:
                pass 

        except Exception as E:
            Warn('Failed to validate ' + self.name + ' map ' + str(m) + ': ' + str(E))
            return False
        return True

    def validateMapList(self):
        numEntries = len(self.maps)
        numValidated = 0
        mapsValidated = []
        Debug(self.name + ' map list: validating ' + str(numEntries) + ' entries')
        for m in self.maps:
            if self.validateMap(m):
                mapsValidated = mapsValidated + [m]
                numValidated = numValidated + 1
        Debug(self.name + ' map list: validated ' + str(numValidated) + ' out of ' + str(numEntries) + ' entries')
        if (numValidated < numEntries) :
            Warn(self.name + ' map list: ' + str(numEntries - numValidated) + ' entries were not correct')
        self.maps = []
        for m in mapsValidated:
            myMap = self.findAndReplaceExistingMap(m)
            if myMap == None:
                self.maps = self.maps + [m]
            else:
                if self.compareMaps(m,myMap):
                    Warn(self.name + ' map ' + mapName(myMap) + ' is already present, ignoring duplicate ' + mapName(m))
                else:
                    Warn(self.name + ' map ' + mapName(myMap) + ' is already present, ignoring conflicting ' + mapName(m))
        Debug(self.name + ' map list: found ' + str(len(self.maps)) + ' unique entries')
        if len(self.maps) < 1:
            self.valid = False

    def updateMapFromRemote(self, m, remote):
        myMap = self.findAndReplaceExistingMap(m)
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
        if not remote.valid:
            Warn('UPDATE: failed due to not having a valid remote map list')
            return False
        try:
            if not remote.update():
                raise OlmappyUpdateError('remote map list could not be updated')
            for m in remote.maps:
                if not Filter.apply(m):
                    continue
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
        Info('UPDATE: ' + str(cntNew) + ' new, ' + str(cntUp) + ' updated, ' + str(cntFail) + ' failed')
        return res

    def getUnindexedFiles(self, d, hidden = 0):
        files = []
        cntAlready = 0
        cntFail = 0
        try:
            for fname in os.listdir(d):
                fullname = d + fname
                try:
                    if equalFileNames(fname, self.indexName):
                        continue
                    if stat.S_ISREG(os.lstat(fullname).st_mode):
                        if hidden > 0:
                            m = self.findMapByHiddenFileName(fname)
                        else:
                            m = self.findMapByFileName(fname)
                        if m == None:
                            Debug('file "' + fullname + '" not in index')
                            files = files + [fname]
                        else:
                            Debug('file "' + fullname + '" already in index')
                            cntAlready = cntAlready + 1
                    else:
                        Debug('ignoring non-file "' + fullname + '"')
                except Exception as E:
                    Warn('failed to classify "'+fullname+'": ' + str(E))
                    cntFail = cntFail + 1
        except Exception as E:
            Warn('failed to scan directory "'+d+'": ' + str(E))
        return files, cntAlready, cntFail

    def importDirFromRemote(self, d, remote, hidden=0):
        cntImp = 0
        cntIgn = 0
        cntReplace = 0
        remote.update()
        if not remote.valid:
            Warn('IMPORT: failed due to not having a valid remote map list')
            return

        files, cntAlready, cntFail = self.getUnindexedFiles(d, hidden)
        for fname in files:
            fullname = d + fname
            try:
                Debug('IMPORT: file "' + fullname + '" not yet known')
                if hidden>0:
                    fname2 = self.RemoveFilenameDecoration(fname)
                else:
                    fname2 = fname
                newMap = remote.findMapByFileName(fname2)
                if newMap != None:
                    if Filter.apply(newMap) == None:
                        newMap = None
                if newMap == None:
                    text = 'IMPORT: file "' + fullname + '" not on remote map list'
                    if Config.settings['removeUnknownMaps']:
                        try:
                            newMap = {}
                            newMap['id'] = 'UNKNOWNID'
                            newMap['filename'] = fname
                            newMap['hidden'] = hidden
                            self.doReplaceMap(newMap)
                            cntReplace = cntReplace + 1
                        except Exception as E:
                            Warn(text + ', FAILED to remove to replaced map section')
                            cntFail = cntFail + 1
                    else:
                        Info(text + ', ignoring')
                        cntIgn = cntIgn + 1
                else:
                    newMap['hidden'] = hidden
                    if self.validateMap(newMap):
                        self.maps = self.maps + [newMap]
                        cntImp = cntImp + 1
                        Info('IMPORT: file "' + fullname + '" imported')
                    else:
                        Warn('IMPORT: file "' + fullname + '" did not match info from server')
                        cntMismatch = cntMismatch + 1
            except Exception as E:
                Warn('IMPORT: failed to import "'+fullname+'": ' + str(E))
                cntFail = cntFail + 1
        Debug('IMPORT: directory "' + d + '": ' + str(cntImp) + ' imported, ' + str(cntAlready) + ' already indexed, ' + str(cntIgn) + ' ignored, ' + str(cntReplace) + ' replaced, ' + str(cntFail) + ' failed to import')
        return cntAlready, cntImp, cntIgn, cntReplace, cntFail


    def importFromRemote(self, remote):
        cntAlready = 0
        cntImp = 0
        cntIgn = 0
        cntReplace = 0
        cntFail = 0
        a,b,c,d,e = self.importDirFromRemote(self.mapDir, remote)
        cntAlready = cntAlready + a
        cntImp = cntImp + b
        cntIgn = cntIgn + c
        cntReplace = cntReplace + d
        cntFail = cntFail + e
        a,b,c,d,e = self.importDirFromRemote(self.mapDir + self.hiddenDir, remote, 1)
        cntAlready = cntAlready + a
        cntImp = cntImp + b
        cntIgn = cntIgn + c
        cntReplace = cntReplace + d
        cntFail = cntFail + e
        Info('IMPORT: ' + str(cntImp) + ' imported, ' + str(cntAlready) + ' already indexed, ' + str(cntIgn) + ' ignored, ' + str(cntReplace) + ' replaced, ' + str(cntFail) + ' failed to import')

    def hideMap(self, m, doHide = True):
        src = self.GetMapPath(m)
        dst = self.GetMapPathAs(m, hidden=doHide)
        if src != dst:
            self.RenameMap(src, dst)
        m['hidden'] = 1 if doHide else 0

    def hideMaps(self, doHide = True):
        name = 'HIDE' if doHide else 'UNHIDE'
        state = 'HIDDEN' if doHide else 'UNHIDDEN'
        cntHidden = 0
        cntAlready = 0
        cntIgn = 0
        cntFail = 0
        if Filter.isEmpty():
            raise OlmappyParseError(name + ': no filter specified, use --all to apply to all')
        for m in self.maps:
            if not Filter.apply(m):
                cntIgn = cntIgn + 1
                continue
            if (m['hidden'] > 0) == doHide:
                Debug(name + ': map ' + mapName(m) + ' is already ' + state)
                cntAlready = cntAlready + 1
                continue
            try:
                self.hideMap(m, doHide)
                Info(name + ': map ' + mapName(m) + ' is now ' + state)
                cntHidden = cntHidden + 1
            except Exception as E:
                Warn(name + ': map ' + mapName(m) + ' failed to ' +name.lower() + ': ' + str(E))
                cntFail = cntFail + 1
        Info(name + ': ' + str(cntHidden) + ' ' + state.lower()+ ', ' + str(cntAlready) + ' already ' + state.lower() + ', ' + str(cntIgn) + ' unchanged, ' + str(cntFail) + ' failed to ' +name.lower())

    def hideImportMaps(self, hideMaps):
        cntFiltered = 0
        cntInvalid = 0
        cntNotPresent = 0
        cntKept = 0
        cntHidden = 0
        cntUnhidden = 0
        cntFail = 0
        for m in hideMaps:
            if not Filter.apply(m):
                cntFiltered = cntFiltered + 1
                continue
            myMap = None
            if 'url' in m:
                myMap = self.findMapByURL(m['url'])
            elif 'id' in m:
                myMap = self.findMapById(m['id'])
            elif 'filename' in m:
                myMap = self.findMapByFileName(m['filename'])
            else:
                Warn('HIDEIMPORT: map ' + str(m) + 'lacks a proper identification, ignored as invalid')
                cntInvalid = cntInvalid + 1
                continue
            if myMap == None:
                Debug('HIDEIMPORT: map ' + mapName(m) + ' is not locally available, ignored')
                cntNotPresent = cntNotPresent + 1
                continue
            if 'size' in m:
                if myMap['size'] != m ['size']:
                    Warn('HIDEIMPORT: map ' + mapName(m) + ' has different size than ours, ignored as invalid')
                    cntInvalid = cntInvalid + 1
                    continue
            if 'mtime' in m:
                if myMap['mtime'] != m ['mtime']:
                    Warn('HIDEIMPORT: map ' + mapName(m) + ' has different mtime than ours, ignored as invalid')
                    cntInvalid = cntInvalid + 1
                    continue

            if 'hidden' not in m:
                Warn('HIDEIMPORT: map ' + mapName(m) + ' has no hidden state to import, ignored as invalid')
                cntInvalid = cntInvalid + 1
                continue
            if m['hidden'] > 0:
                m['hidden'] = 1
            else:
                m['hidden'] = 0
            if Cmd.args.reverse == True:
                m['hidden'] = 1 - m['hidden']
            if m['hidden'] > 0:
                state = 'HIDDEN'
            else:
                state = 'UNHIDDEN'
            if m['hidden'] == myMap['hidden']:
                Debug('HIDEIMPORT: map ' + mapName(m) + ' kept as ' + state)
                cntKept = cntKept + 1
                continue
            try:
                if m['hidden'] == 0:
                    self.hideMap(myMap, False)
                    cntUnhidden = cntUnhidden + 1
                else:
                    self.hideMap(myMap, True)
                    cntHidden = cntHidden + 1
                Info('HIDEIMPORT: map ' + mapName(myMap) + ' is now ' + state)
            except Exception as E:
                Warn(name + ': map ' + mapName(m) + ' failed to set to ' +state + ': ' + str(E))
                cntFail = cntFail + 1
        Info('HIDEIMPORT: ' + str(cntHidden) + ' hidden, ' + str(cntUnhidden) + ' unhidden, ' + str(cntKept) + ' unchanged, ' + str(cntNotPresent) + ' not present, ' + str(cntFiltered) + ' filtered, ' + str(cntInvalid) + ' invalid, ' + str(cntFail) + ' failed to change')

    def hideImport(self, filename):
        hideMaps, valid = self.loadMapListFile(filename)
        if len(hideMaps) > 0 and valid:
            self.hideImportMaps(hideMaps)
        else:
            Warn('HIDEIMPORT: no valid maps found')

    def listIgnored(self):
        files, cntAlready, cntFail = self.getUnindexedFiles(self.mapDir)
        for fname in files:
            print('"' + fname + '"')
        Debug('LISTIGNORED: ' + str(len(files)) + ' ignored, ' + str(cntAlready) + ' indexed, ' + str(cntFail) + ' failed')

##############################################################################
# class for managing the remote map server                                   #
##############################################################################

class remoteMapManager(MapManager):
    def __init__(self):
        MapManager.__init__(self)
        self.name = 'remote'
        self.valid = False
        self.listURL = Config.settings['mapServer'] + Config.settings['mapServerListURL']
        certMode = 'CERT_REQUIRED' if Config.settings['verifyCertificates'] else 'CERT_NONE'
        if len(Config.settings['certificateBundle']) > 0:
            self.http = urllib3.PoolManager(cert_reqs=certMode, ca_certs=Config.settings['certificateBundle'])
        else:
            self.http = urllib3.PoolManager(cert_reqs=certMode)

    def getMapList(self):
        url = self.listURL
        try:
            request = self.http.request('GET', url)
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
            raise OlmappyTransferError('failed to GET map list ' + url + ': ' + str(E)) from E

    def validateMapList(self):
        if not self.valid:
            Warn(self.generic + ' map list is not in VALID state')
            return False
        numEntries = len(self.maps)
        numValidated = 0
        mapsValidated = []
        Debug(self.name + ' map list: validating ' + str(numEntries) + ' entries')
        for m in self.maps:
            if self.validateMap(m):
                mapsValidated = mapsValidated + [m]
                numValidated = numValidated + 1
        Debug(self.name + ' map list: validated ' + str(numValidated) + ' out of ' + str(numEntries) + ' entries')
        if (numValidated < numEntries) :
            Warn(self.name + ' map list: ' + str(numEntries - numValidated) + ' entries were not correct')
        self.maps = []
        for m in mapsValidated:
            myMap = self.findMapByFileName(m['filename'])
            if myMap == None:
                self.maps = self.maps + [m]
            else:
                if (myMap['mtime'] < m['mtime']) :
                    Warn(self.name + ' map ' + mapName(m) + ' is newer than conflicting ' + mapName(myMap) + ', replacing it')
                    self.maps.remove(myMap)
                    self.maps = self.maps + [m]
                else:
                    Warn(self.name + ' map ' + mapName(m) + ' is older than conflicying ' + mapName(myMap) + ', ignoring it')
        if (len(self.maps) < 1):
            Warn(self.name + ' map list: no valid entries found')
            self.valid = False
        else:
            Info(self.name + ' map list: ' +str(len(self.maps)) + ' unique entries found')
        return self.valid

    def update(self, forceRefresh = False):
        if forceRefresh:
            self.valid = False
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
            url = Config.settings['mapServer'] +  m['url']
            outFile = open(outFileName, 'wb')
            Debug('attempting to download ' + url)
            request = self.http.request('GET', url, preload_content = False)
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

##############################################################################
# class for string filter                                                    #
##############################################################################

class StringFilter:
    def __init__(self, value, exact = False, caseSensitive = None):
        self.value = value
        self.exact = exact
        self.caseSensitive = caseSensitive

    def validate(self, caseSensitive):
        if self.caseSensitive == None:
            self.caseSensitive = caseSensitive
        if not self.caseSensitive:
            self.value = self.value.casefold()

    def apply(self, s):
        s2 = s if self.caseSensitive else s.casefold()
        if self.exact:
            return (self.value == s2)
        else:
            return (self.value in s2)

##############################################################################
# class for map filtering                                                    #
##############################################################################

class MapFilter:
    def __init__(self):
        self.names = []
        self.exactnames = []
        self.filenames = []
        self.exactfilefilenames = []
        self.types = 0
        self.time_before = None
        self.time_after = None
        self.hidden = False
        self.unhidden = False
        self.explicitApplyToAll = False
        self.filterCaseSensitive = False
        self.filenameCaseSensitive = False

    @staticmethod
    def validateStringFilter(filterList, caseSensitive):
        for filter in filterList:
            filter.validate(caseSensitive)

    @staticmethod
    def inString(filterList, s):
        if len(filterList) < 1:
            return True
        for f in filterList:
            if f.apply(s):
                return True
        return False

    @staticmethod
    def inStringList(filterList, sList):
        if len(sList) < 1:
            return False
        if len(filterList) < 1:
            return True
        for s in sList:
            if MapFilter.inString(filterList, s):
                return True
        return False

    def validate(self):
        self.filterCaseSensitive = Config.settings['filterCaseSensitive']
        self.filenameCaseSensitive = Config.settings['filenameCaseSensitive'] and self.filterCaseSensitive
        self.validateStringFilter(self.names, self.filterCaseSensitive)
        self.validateStringFilter(self.filenames, self.filenameCaseSensitive)

    def isEmpty(self):
        if len(self.names) > 0:
            return False
        if len(self.filenames) > 0:
            return False
        if self.types != 0:
            return False
        if self.time_before != None or self.time_after != None:
            return False
        if self.explicitApplyToAll:
            return False
        return True

    def apply(self, m):
        if self.types != 0:
            if (m['types'] & self.types) == 0:
                return False
            if len(self.names) > 0:
                found = False
                for l in m['levels']:
                    t = MapType.MapTypeString(l['type'])
                    if (t & self.types) == t:
                        if self.inString(self.names, l['name']):
                            found = True
                            break
                if not found:
                    return False
        else:
            if not self.inStringList(self.names, m['names']):
                return False
        if not self.inString(self.filenames, m['filename']):
            return False
        if self.time_before != None:
            if m['mtime'] >= self.time_before:
                return False
        if self.time_after != None:
            if m['mtime'] < self.time_after:
                return False
        if self.hidden and (m['hidden'] < 1):
                return False
        if self.unhidden and (m['hidden'] > 0):
                return False
        return True

##############################################################################
# class for configuration settings                                           #
##############################################################################

class Settings:
    def __init__(self):
        self.settings = {}
        self.settings['mapPath'] = ' /usr/share/Revival/Overload/'
        self.settings['mapServer'] = 'https://overloadmaps.com'
        self.settings['mapServerListURL'] = '/data/all.json'
        self.settings['logLevel'] = LogLevel.INFO
        self.settings['filenameCaseSensitive'] = False
        self.settings['filterCaseSensitive'] = False
        self.settings['removeUnknownMaps'] = False
        self.settings['autoImport'] = True
        self.settings['configFile'] = os.getenv('HOME', '.') +  '/.config/olmappy.json'
        self.settings['verifyCertificates'] = True
        self.settings['certificateBundle'] = ''

    def applySettings(self, newSettings):
        for name, value in newSettings.items():
            self.settings[name] = value

    def validatebool(self, name):
        if type(self.settings[name]) is str:
            self.settings[name] = stringAsBool(self.settings[name])

    def validateint(self, name):
        if type(self.settings[name]) is str:
            self.settings[name] = int(self.settings[name])

    def validateSettings(self):
        if len(self.settings['mapPath']) < 1:
            self.settings['mapPath'] = './'
            Warn('invalid mapPath, using "' + self.settings['mapPath'] + '" instead')
        else:
            if self.settings['mapPath'][-1] != '/':
                self.settings['mapPath'] = self.settings['mapPath'] + '/'
        self.validatebool('filenameCaseSensitive')
        self.validatebool('filterCaseSensitive')
        self.validatebool('autoImport')
        self.validatebool('verifyCertificates')
        self.validateint('logLevel')

    def load(self, configFile = None, errorOk = True):
        newSettings = {}
        if configFile == None:
            configFile = self.settings['configFile']
        try:
            cf = open(file = configFile, mode = 'rt', encoding = 'utf-8')
            newSettings = json.load(cf)
            cf.close()
            self.applySettings(newSettings)
            self.validateSettings()
            Debug('loaded config file "' + configFile + '"')
            if 'configFile' in newSettings:
                if not equalFileNames(newSettings['configFile'], configFile):
                    Debug('recursively loading config file "' + newSettings['configFile'] + '"')
                    self.load(newSettings['configFile'], False)
        except FileNotFoundError as E:
            text = 'config file "' + configFile + '" could not be found: ' + str(E)
            if errorOk:
                Debug(text)
            else:
                Warn(text)
                raise OlmappyConfigError(text) from E
        except Exception as E:
            text = 'config file "' + configFile + '" could not be parsed: ' + str(E)
            if errorOk:
                Debug(text)
            else:
                Warn(text)
                raise OlmappyConfigError(text) from E

    def save(self, configFile = None):
        if configFile == None:
            configFile = self.settings['configFile']
        cf = open(file = configFile, mode = 'wt', encoding = 'utf-8')
        writeSettings = self.settings.copy()
        del writeSettings['configFile']
        json.dump(writeSettings, cf, indent=4)
        cf.close()

    def show(self,):
        print(json.dumps(self.settings, indent=4))

##############################################################################
# commandline parsing                                                        #
##############################################################################

class Commandline:
    def __init__(self):
        self.parser = argparse.ArgumentParser(description='Manage Overload maps.')
        ophelp = 'the operation to execute, must be one of: '
        cnt =0
        for name,value in Operation.__members__.items():
            if cnt > 0:
                ophelp = ophelp + ', '
            ophelp = ophelp +  name
            cnt = cnt + 1
        ophelp = ophelp + '. Default is %(default)s.'

        self.parser.add_argument('operation',
                                 type=Operation.OperationString,
                                 nargs='?',
                                 default = 'UPDATE',
                                 help = ophelp)
        self.parser.add_argument('-s', '--set',
                                 nargs = 2,
                                 metavar = ('NAME', 'VALUE'),
                                 action = 'append',
                                 help = 'set configuration option NAME to VALUE')
        self.parser.add_argument('-n', '--name',
                                 nargs = 1,
                                 action = 'append',
                                 help = 'add filter for map name')
        self.parser.add_argument('-N', '--exact-name',
                                 nargs = 1,
                                 action = 'append',
                                 help = 'add filter for exact map name')
        self.parser.add_argument('-f', '--filename',
                                 nargs = 1,
                                 action = 'append',
                                 help = 'add filter for map filename')
        self.parser.add_argument('-F', '--exact-filename',
                                 nargs = 1,
                                 action = 'append',
                                 help = 'add filter for exact map filename')
        self.parser.add_argument('-t', '--type',
                                 type = MapType.MapTypeString,
                                 nargs = 1,
                                 action = 'append',
                                 help = 'add filter for map type')
        self.parser.add_argument('-b', '--time-before',
                                 type = parseDateTime,
                                 metavar = 'DATETIME',
                                 nargs = 1,
                                 help = 'add filter for map mtime: must be before given DATETIME')
        self.parser.add_argument('-a', '--time-after',
                                 type = parseDateTime,
                                 metavar = 'DATETIME',
                                 nargs = 1,
                                 help = 'add filter for map mtime: must be at or after given DATETIME')
        self.parser.add_argument('-H', '--hidden',
                                 action = 'store_true',
                                 help = 'add filter: only apply to hidden maps')
        self.parser.add_argument('-U', '--unhidden',
                                 action = 'store_true',
                                 help = 'add filter: only apply to not hidden maps')
        self.parser.add_argument('-A', '--all',
                                 action = 'store_true',
                                 help = 'for HIDE or UNHIDE operations, when no filter is specified: really apply to ALL maps')
        self.parser.add_argument('-E', '--export-file',
                                 action = 'store',
                                 nargs = 1,
                                 default = 'olmappyExport.json',
                                 help = 'for EXPORT... operations: the filename to write to, default is "%(default)s".')
        self.parser.add_argument('-I', '--import-file',
                                 action = 'store',
                                 nargs = 1,
                                 default = 'olmappyExport.json',
                                 help = 'for IMPORT... operations: the filename to read from, default is "%(default)s".')
        self.parser.add_argument('--reverse',
                                 action = 'store_true',
                                 default = 'olmappyExport.json',
                                 help = 'for HIDEIMPORT: reverse the "hidden" state of the imported map files.')
        self.parser.add_argument('--version', action='version', version='%(prog)s 1.1')
        self.parser.epilog = 'See README.md for details.'

    def parse(self):
        self.args = self.parser.parse_args()

        if self.args.set != None:
            for s in self.args.set:
                if s[0] == 'configFile':
                    Config.settings[s[0]]=s[1]
                    Config.validateSettings()

        Config.load()

        if self.args.set != None:
            for s in self.args.set:
                Config.settings[s[0]]=s[1]
            Config.validateSettings()
        if self.args.type != None:
            for t in self.args.type:
                Filter.types = Filter.types | t[0]
        if self.args.name != None:
            for n in self.args.name:
                Filter.names = Filter.names + [StringFilter(n[0])]
        if self.args.filename != None:
            for n in self.args.filename:
                Filter.filenames = Filter.filenames + [StringFilter(n[0])]
        if self.args.exact_name != None:
            for n in self.args.exact_name:
                Filter.names = Filter.names + [StringFilter(n[0], exact=True)]
        if self.args.exact_filename != None:
            for n in self.args.exact_filename:
                Filter.filenames = Filter.filenames + [StringFilter(n[0], exact=True)]
        if self.args.time_before != None:
            Filter.time_before = self.args.time_before[0]
        if self.args.time_after != None:
            Filter.time_after = self.args.time_after[0]
        Filter.hidden = self.args.hidden
        Filter.unhidden = self.args.unhidden
        Filter.explicitApplyToAll = self.args.all
        Filter.validate()
        return self.args.operation

##############################################################################
# operation control                                                          #
##############################################################################

class Operation(enum.IntEnum):
    IMPORT = 1
    UPDATE = 2
    LISTLOCAL = 3
    LISTREMOTE = 4
    HIDE = 5
    UNHIDE = 6
    WRITECONFIG = 7
    SHOWCONFIG = 8
    LISTIGNORED = 9
    EXPORTLIST = 10
    HIDEIMPORT = 11

    def apply(self):
        operations = [
            self.doHelp,
            self.doImport,
            self.doUpdate,
            self.doListLocal,
            self.doListRemote,
            self.doHide,
            self.doUnhide,
            self.doWriteConfig,
            self.doShowConfig,
            self.doListIgnored,
            self.doExportList,
            self.doHideImport
        ]

        res = 999
        try:
            res = operations[self.value]()
            if res != 0:
                Error('Operation ' + self.asString() + ' failed with code: ' + str(res))
        except Exception as E:
            Error('Operation ' + self.asString() + ' failed: ' + str(E))
            res = 998
        return res

    def asString(self):
        for name, value in Operation.__members__.items():
            if value == self.value:
                return name
        raise OlmappyParseError('Operation ' + str(self.value)+ ' is not valid')

    @classmethod
    def OperationString(cls,s):
        try:
            return cls.__members__[s.upper()]
        except KeyError as E:
            raise ValueError from E

    def doHelp(self):
        print('xxx')
        return 0

    def doImport(self):
        local = localMapManager()
        remote = remoteMapManager()
        local.update()
        local.importFromRemote(remote)
        local.saveMapList()
        return 0

    def doUpdate(self):
        local = localMapManager()
        remote = remoteMapManager()
        local.update()
        if Config.settings['autoImport']:
            local.importFromRemote(remote)
        local.updateFromRemote(remote)
        local.saveMapList()
        return 0

    def doList(self, local=True, doExport=False):
        manager = localMapManager() if local else remoteMapManager()
        manager.update()
        manager.listMaps(doExport)
        return 0

    def doListLocal(self):
        return self.doList(True)

    def doListRemote(self):
        return self.doList(False)

    def doHide(self):
        local = localMapManager()
        local.update()
        local.hideMaps(True)
        local.saveMapList()
        return 0

    def doUnhide(self):
        local = localMapManager()
        local.update()
        local.hideMaps(False)
        local.saveMapList()
        return 0

    def doWriteConfig(self):
        Config.save()
        return 0

    def doShowConfig(self):
        Config.show()
        return 0

    def doListIgnored(self):
        local = localMapManager()
        local.update()
        local.listIgnored()
        return 0

    def doExportList(self):
        return self.doList(True, True)

    def doHideImport(self):
        local = localMapManager()
        local.update()
        local.hideImport(Cmd.args.import_file[0])
        local.saveMapList()
        return 0


##############################################################################
# main program entry point                                                   #
##############################################################################

Config = Settings()
Filter = MapFilter()
Cmd = Commandline()

operation = Cmd.parse()

exit(operation.apply())
