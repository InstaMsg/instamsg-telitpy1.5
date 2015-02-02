# -*- coding: utf-8 -*-
import at
import MOD
import exceptions
    

class TimeError(Exception):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
error = TimeError

def time():
    try:
        return MOD.secCounter()
    except Exception, e:
        raise error('Time:: Unable to get time. %s' %repr(e))
    
def asctime():
    try:
        return at.getRtcTime()
    except Exception, e:
        raise error('Time:: Unable to get time. %s' %repr(e))    

def sleep(sec):
    MOD.sleep(int(sec)*10)
    
def getTimeAndOffset():
    try:
        t=asctime()
        now = localtime(t)
        timestr = "%04d%02d%02d%01d%02d%02d%02d" % (now[0],now[1],(now[2]),(now[6]),now[3],now[4],now[5])
        offset = str(__getOffset(t))
        return [timestr, offset]
    except Exception, e:
        raise error('Time:: Unable to parse time.')
    
def localtime(time=None):
    if(time is None):
        time=asctime()
    t=time[0:-3].split(',')
    date=map(int,t[0].split('/'))
    time=map(int,t[1].split(':'))
    date[0]=date[0] +2000
    time.append(weekDay(date)[0])
    return (date + time)

def weekDay(date):
    year=date[0]
    month=date[1]
    day=date[2]
    offset = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    week   = {0:'Sunday', 
              1:'Monday', 
              2:'Tuesday', 
              3:'Wednesday', 
              4:'Thursday',  
              5:'Friday', 
              6:'Saturday'}
    afterFeb = 1
    if month > 2: afterFeb = 0
    aux = year - 1700 - afterFeb
    # dayOfWeek for 1700/1/1 = 5, Friday
    dayOfWeek  = 5
    # partial sum of days betweem current date and 1700/1/1
    dayOfWeek = dayOfWeek+(aux + afterFeb) * 365                  
    # leap year correction    
    dayOfWeek = dayOfWeek + aux / 4 - aux / 100 + (aux + 100) / 400     
    # sum monthly and day offsets
    dayOfWeek = dayOfWeek + offset[month - 1] + (day - 1) 
    dayOfWeek = dayOfWeek%7
    return dayOfWeek, week[dayOfWeek]

def __getOffset(time):
    offset = int(time[-3:])*15*60
    return offset

