class Observer:
    
    def notify(observable_name):
        raise NotImplementedError()


class UnknownObserverError(LookupError):
    
    def __init__(self, observer, observable_name=None):
        self.observer = observer
        self.observable_name = observable_name
        if observable_name is None:
            observable_name = 'all'
        message = 'The oberserver {} for {} is unknown'.format(observer, observable_name)
        super().__init__(message)



class Observable:
    
    def __init__(self):
        self._observers = {}
        self._everything_observers = []
        
    
    ## observer methods
    
    def add_observer(self, observer, observable_name=None):
        ## get everything observer list if no observable name is specified
        if observable_name is None:
            observer_list = self._everything_observers
        
        ## get specific observer list if observable name is specified
        else:
            try:
                observer_list = self._observers[observable_name]
            except KeyError:
                observer_list = []
                self._observers[observable_name] = observer_list
        
        ## add observer
        observer_list.append(observer)
        
    
    def remove_observer(self, observer, observable_name=None):
        ## get everything observer list if no observable name is specified
        if observable_name is None:
            observer_list = self._everything_observers
        
        ## get specific observer list if observable name is specified
        else:
            try:
                observer_list = self._observers[observable_name]
            except KeyError:
                raise UnknownObserverError(observer, observable_name=observable_name)
        
        ## remove observer
        try:
            observer_list.remove(observer)
        except ValueError:
            raise UnknownObserverError(observer, observable_name=observable_name)
        
        ## remove also list if empty
        if observable_name is not None and len(observer_listobserver_list) == 0:
            del self._observers[observable_name]

    
    def get_observers(self, observable_name=None, include_everything_observers=True):
        ## get specifiy observer
        if observable_name is not None:
            try:
                specific_observer = self._observers[observable_name]
            except KeyError:
                specific_observer = []
        
        ## get all observer
        if include_everything_observers:
            all_observer = self._everything_observers.copy()
        else:
            all_observer = []
        all_observer.extend(specific_observer)
        
        return all_observer
    
    
    def _notify_observers(self, observable_name=None, include_everything_observers=True):
        for observer in self.get_observers(observable_name=observable_name, include_everything_observers=include_everything_observers):
            observer(observable_name)
    
    
    def copy_observers_to(self, observable):
        observable._everything_observers.extend(self._everything_observers)

        for observable_name, observer in self._observers.items():
            observable.add_observer(observer, observable_name=observable_name)
    
    
    ## get and set observable_names method
    
    def _set_value(self, observable_name, new_value):
        raise NotImplementedError()
    
    def _del_value(self, observable_name):
        raise NotImplementedError()
        
    def _has_value(self, observable_name):
        raise NotImplementedError()
    
    def _get_value(self, observable_name):
        raise NotImplementedError()
    
    
    
    def _set_observable(self, observable_name, new_value):
        
        ## check old value
        if self._has_value(observable_name):
            old_value = self.new_value(observable_name)
            
            ## set only if different value
            must_set = np.any(new_value != old_value)
            if must_set:
                
                ## if values are observable_names with observers call associated observers of sub observable_names
                if isinstance(old_value, Observable) and isinstance(new_value, Observable):
                    ## copy observer
                    old_value.copy_observers_to(new_value)
                    
                    ## notify old observer
                    old_value._notify_observers(observable_name=None, include_everything_observers=True)
                    for observable_name in old_value._observers.keys():
                        old_has_value = old_value._has_value(observable_name)
                        new_has_value = new_value._has_value(observable_name)
                        if old_has_value != new_has_value or (old_has_value and new_has_value and np.any(old_value._get_value(observable_name) != new_value._get_value(observable_name))):
                            old_value._notify_observers(observable_name=observable_name, include_everything_observers=False)
        else:
            must_set = True
        
            
        ## set new observable_name value and call observer
        if must_set:
            self._set_value(observable_name, new_value)
            self._notify_observers(observable_name)
    
    
    def _del_observable(self, observable_name):
        self._del_value(observable_name)
        self._notify_observers(observable_name)



def observable_mutable_mapping_class(MutableMappingClass):
    
    class ObservableMutableMapping(Observable, MutableMappingClass):
        
        def __init__(self, *args, **kwargs):
            Observable.__init__(self)
            MutableMappingClass.__init__(self, *args, **kwargs)
        
        
        def __setitem__(self, key, value):
            self._set_observable(key, value)
    
        def __delitem__(self, key):
            self._del_observable(key)
        
        
        def _set_value(self, key, value):
            super().__setitem__(key, value)
        
        def _del_value(self, key):
            super().__delitem__(key)
            
        def _has_value(self, key):
            super().__contains__(key)
        
        def _get_value(self, key):
            return super().__getitem__(key)
        
    
    return ObservableMutableMapping



OberservableDict = observable_mutable_mapping_class(Dict)




def observable_attributes(original_class):
    class NewClass(object):
        
        def __init__(self, *args, **kwargs):
            self.original_instance = original_class(*args, **kwargs)
        
        def __getattribute__(self, s):
            """
            this is called whenever any attribute of a NewClass object is accessed. This function first tries to 
            get the attribute off NewClass. If it fails then it tries to fetch the attribute from self.original_instance (an
            instance of the decorated class). If it manages to fetch the attribute from self.original_instance, and 
            the attribute is an instance method then `time_this` is applied.
            """
            try:    
                x = super(NewClass, self).__getattribute__(s)
            except AttributeError:      
                pass
            else:
                return x
            x = self.original_instance.__getattribute__(s)
            if type(x) == type(self.__init__): # it is an instance method
                return time_this(x)                 # this is equivalent of just decorating the method with time_this
            else:
                return x
    return NewClass