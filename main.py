#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from google.appengine.ext import webapp
from google.appengine.ext.webapp import util
from google.appengine.ext import db

import jinja2
import webapp2
import logging
import json
import datetime
import sys
import calendar
import os

CLASS_TYPE_STR = '__class'
CLASS_VALUE_STR = 'value'
ID_STR = '__id'

jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))

def hook(dct):
    clsType = dct[CLASS_TYPE_STR]
    if clsType == 'date':
        return datetime.date.fromtimestamp(dct[CLASS_VALUE_STR])
    if clsType == 'time':
        number = dct[CLASS_VALUE_STR]
        hour = number / 60
        minute = number % 60
        return datetime.time(hour, minute)
    if clsType == 'email':
        return db.Email(dct[CLASS_VALUE_STR])
    if clsType == 'phone':
        return db.PhoneNumber(dct[CLASS_VALUE_STR])
    elif clsType == 'rating':
        return db.Rating(dct[CLASS_VALUE_STR])
     # The constructor can't handle the clsType tag, so delete it!
    dictCopy = dict((key,value) for key,value in dct.iteritems() if not key.startswith('__'))
    return globals()[clsType](**dictCopy).put()

class DataEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.date):
            return {CLASS_TYPE_STR: 'date', CLASS_VALUE_STR:calendar.timegm(obj.timetuple())}
        elif isinstance(obj, datetime.time):
            return {CLASS_TYPE_STR: 'time', CLASS_VALUE_STR:obj.hour * 60 + obj.minute}
        elif isinstance(obj, db.PhoneNumber):
            return {CLASS_TYPE_STR: 'date', CLASS_VALUE_STR:obj}
        elif isinstance(obj, db.Email):
            return {CLASS_TYPE_STR: 'email', CLASS_VALUE_STR: obj}
        elif isinstance(obj,db.Rating):
            return {CLASS_TYPE_STR: 'rating', CLASS_VALUE_STR: obj}
        elif isinstance(obj,db.Model):
            dictCopy = obj._entity
            dictCopy[CLASS_TYPE_STR] = obj.kind()
            return dictCopy
        elif isinstance(obj,db.Key):
            dictCopy = db.get(obj)._entity
            dictCopy[CLASS_TYPE_STR] = obj.kind()
            return dictCopy

class Hours(db.Model):
    """Models the hours of operation"""
    open_time = db.TimeProperty()
    close_time = db.TimeProperty()    

class DateRule(db.Model):
    """Models an exception from the regular hours of operation"""
    date = db.DateProperty()
    new_hours = db.ReferenceProperty(Hours)

class WeeklyHours(db.Model):
    """Models the hours of operation"""
    monday = db.ReferenceProperty(Hours, collection_name="monday")
    tuesday = db.ReferenceProperty(Hours, collection_name="tuesday")
    wednesday = db.ReferenceProperty(Hours, collection_name="wednesday")
    thursday = db.ReferenceProperty(Hours, collection_name="thursday")
    friday = db.ReferenceProperty(Hours, collection_name="friday")
    saturday = db.ReferenceProperty(Hours, collection_name="saturday")
    sunday = db.ReferenceProperty(Hours, collection_name="sunday")
    exceptions = db.ListProperty(db.Key)

class Winery(db.Model):
    """Models a winery"""
    name = db.StringProperty()
    description = db.TextProperty()
    rating = db.RatingProperty()
    email = db.EmailProperty()
    phone = db.PhoneNumberProperty()
    hours = db.ReferenceProperty(WeeklyHours)
    
class Event(db.Model):
    """Models an event"""
    title = db.StringProperty(required=True);
    description = db.StringProperty();
    start_date = db.DateProperty();
    start_time = db.TimeProperty();
    end_date = db.DateProperty();
    end_time = db.TimeProperty();

class RestServer(webapp.RequestHandler):
    '''
    This class provides a RESTful API that we can use to
    add new tags to as well as view relevant data.
    '''
    
    log = logging.getLogger('API')

    def post(self):
        #Load the JSON values that were sent to the server
        newKey = json.loads(self.request.body, object_hook=hook)
        self.log.info("imported: " + str(dir(newKey)))

        #Returns the ID that was created
        self.response.write(str(newKey.id()))
    
    def get(self):
        #pop off the script name ('/api')
        self.request.path_info_pop()

        #forget about the leading '/' and seperate the Data type and the ID
        split = self.request.path_info[1:].split('/')
        self.log.info('after split:' + str(split))
        #If no ID, then we will return all objects of this type
        if len(split) == 1:
            everyItem = []
            #Finds the class that was specified from our list of global objects
            #and create a Query for all of these objects. Then iterate through
            #and collect the IDs
            for item in globals()[split[0]].all():
                everyItem.append(item)
            #Write JSON back to the client
            self.response.write(json.dumps(everyItem, cls=DataEncoder))
        else:
            #Convert the ID to an int, create a key and retrieve the object
            retrievedEntity = db.get(db.Key.from_path(split[0], int(split[1])))
            #Return the values in the entity dictionary
            self.response.write(json.dumps(retrievedEntity, cls=DataEncoder))
    
    def delete(self):
        #pop off the script name
        self.request.path_info_pop()

        #forget about the leading '/'
        split = self.request.path_info[1:].split(':')
        if len(split) == 1:
            for key in globals()[split[0]].all(keys_only=True):
                db.delete(key)
        else:
            db.delete(db.Key.from_path(split[0], int(split[1])))

class View(webapp.RequestHandler):
    def get(self):
        template_values = {'wineries':[winery.key().id()  for winery in Winery.all()]}
        template = jinja_environment.get_template('index.html')
        self.response.out.write(template.render(template_values))

    def post(self):
        m = Hours(open_time=self.req.get('monday_open'),close_time=self.req.get('monday_close')).put()
        t = Hours(open_time=self.req.get('tuesday_open'),close_time=self.req.get('tuesday_close')).put()
        w = Hours(open_time=self.req.get('wednesday_open'),close_time=self.req.get('wednesday_close')).put()
        th = Hours(open_time=self.req.get('thursday_open'),close_time=self.req.get('thursday_close')).put()
        f = Hours(open_time=self.req.get('friday_open'),close_time=self.req.get('friday_close')).put()
        s = Hours(open_time=self.req.get('saturday_open'),close_time=self.req.get('saturday_close')).put()
        su = Hours(open_time=self.req.get('sunday_open'),close_time=self.req.get('sunday_close')).put()
        h = WeeklyHours(monday=m,tuesday=t,wednesday=w,thursday=th,friday=f,saturday=s,sunday=su).put()
        
        winery = Winery(name=self.req.get('name'), description=self.req.get('description'), email=self.req.get('email'), phone=self.req.get('phone'), address=self.req.get('address'),hours=h).put()

        template_values = {'wineries':[winery.key().id()  for winery in Winery.all()]}
        template = jinja_environment.get_template('index.html')

        self.response.out.write(template.render(template_values))

app = webapp2.WSGIApplication([('/api.*', RestServer), ('.*',View)],
                                         debug=True)
