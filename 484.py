#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Copyright (c) 2015 by Sanhe Hu
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Author: Sanhe Hu
- Email: husanhe@gmail.com
- Lisence: MIT
    

Introduction
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

dicttree is a node tree data structure pure python implementation.

Every node have its parent (except root node) and children (except leaf node).
And you can add arbitrarily many attributes to node. Attributes can be any data
type in Python.

The dicttree is not a class, but actually a python dict. The way you manipulate 
it is via a bunch of static method class DictTree. Because dict is a mutable 
object in python, so everything you done inside the DictTree.some_method(dict) 
is really taking effect on it.

Because it's a python dict, so you can easily dump it to a file using json 
(if applicable) or pickle.


Understand dicttree
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

definitions

- *root*:        the dict it self
- *branch*:      the set of it's child nodes
- *node*:        a #key : {"_meta": attribute_dict} pair
- *children*:    one of the child node on the branch 
- *parent*:      parent of a node
- *depth*:       root is on depth 0, the children of root is on depth 1, etc...
- *root node*:   type of node that has at least one children
- *leaf node*:   type of node that has no children
    
Let's take a look at an example:

1. the dicttree it self has attributes: a special key ``_rootname`` 
    indicate the name of this tree, and a ``population`` attribute. Attributes 
    are saved in a special dictionary with key ``_meta``.
    
2. the dicttree has two children on depth 1, ``MD`` and ``VA``. Each children 
    has its own attributes: ``name`` and ``population``.
    
3. also childrens on depth 1 can have their own children.

.. code-block:: python

    {
        "_meta": {
            "_rootname": "US",
            "population": 27800000.0
        },
        "MD": {
            "_meta": {
                "name": "maryland",
                "population": 200000
            },
            "bethesta": {
                "_meta": {
                    "name": "montgomery country",
                    "population": 5800
                }
            },
            "germentown": {
                "_meta": {
                    "name": "fredrick country",
                    "population": 1400
                }
            }
        },
        "VA": {
            "_meta": {
                "name": "virginia",
                "population": 100000
            },
            "arlington": {
                "_meta": {
                    "name": "arlington county",
                    "population": 5000
                },
                "crystal plaza": {
                    "_meta": {
                        "name": "Crystal plaza South",
                        "population": 681
                    }
                },
                "loft": {
                    "_meta": {
                        "name": "loft hotel",
                        "population": 216
                    }
                },
                "riverhouse": {
                    "_meta": {
                        "name": "RiverHouse 1400",
                        "population": 437
                    }
                }
            },
            "vienna": {
                "_meta": {
                    "name": "vienna county",
                    "population": 1500
                }
            }
        }
    }


Compatibility
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Python2: Yes
- Python3: Yes


Prerequisites
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- None


Class, method, function, exception
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
"""

from __future__ import print_function
from six import iterkeys, iteritems
import copy
import json

_meta = "_meta"

class DictTree(object):
    """dicttree methods' host class. All method are staticmethod, so we can keep
    the namespace clean.
    """
    @staticmethod
    def initial(key, **kwarg):
        """Create an empty dicttree.

        The root node has a special attribute "_rootname".
        Because root node is the only dictionary doesn't have key. 
        So we assign the key as a special attribute.

        Usage::

            >>> from weatherlab.lib.dtypes.dicttree import DictTree as DT
            >>> d = DT.initial("US)
            >>> d
            {'_meta': {'_rootname': 'US'}}
        """
        d = dict()
        DictTree.setattr(d, _rootname = key, **kwarg)
        return d
    
    @staticmethod
    def setattr(d, **kwarg):
        """Set an attribute.

        set attributes is actually add a special key, value pair in this dict
        under key = "_meta".

        Usage::

            >>> DT.setattr(d, population=27800000)
            >>> d
            {'_meta': {'population': 27800000, '_rootname': 'US'}}
        """
        if _meta not in d:
            d[_meta] = dict()
        for k, v in kwarg.items():
            d[_meta][k] = v

    @staticmethod
    def getattr(d, attribute_name):
        """Get attribute_value from the special ``attributes_dict``.

        Usage::

            >>> DT.getattr(d, "population")
            27800000
        """
        return d[_meta][attribute_name]
 
    @staticmethod
    def add_children(d, key, **kwarg):
        """Add a children with key and attributes. If children already EXISTS, 
        OVERWRITE it.

        Usage::

            >>> from pprint import pprint as ppt
            >>> DT.add_children(d, "VA", name="virginia", population=100*1000)
            >>> DT.add_children(d, "MD", name="maryland", population=200*1000)
            >>> ppt(d)
            {'_meta': {'population': 27800000, '_rootname': 'US'},
             'MD': {'_meta': {'name': 'maryland', 'population': 200000}},
             'VA': {'_meta': {'name': 'virginia', 'population': 100000}}}

            >>> DT.add_children(d["VA"], "arlington", 
                    name="arlington county", population=5000)
            >>> DT.add_children(d["VA"], "vienna", 
                    name="vienna county", population=5000)
            >>> DT.add_children(d["MD"], "bethesta", 
                    name="montgomery country", population=5800)
            >>> DT.add_children(d["MD"], "germentown", 
                    name="fredrick country", population=1400)

            >>> DT.add_children(d["VA"]["arlington"], "riverhouse", 
                    name="RiverHouse 1400", population=437)
            >>> DT.add_children(d["VA"]["arlington"], "crystal plaza", 
                    name="Crystal plaza South", population=681)
            >>> DT.add_children(d["VA"]["arlington"], "loft", 
                    name="loft hotel", population=216)

            >>> ppt(d)
            {'MD': {'_meta': {'name': 'maryland', 'population': 200000},
                    'bethesta': {'_meta': {'name': 'montgomery country',
                                           'population': 5800}},
                    'germentown': {'_meta': {'name': 'fredrick country',
                                             'population': 1400}}},
             'VA': {'_meta': {'name': 'virginia', 'population': 100000},
                    'arlington': {'_meta': {'name': 'arlington county',
                                            'population': 5000},
                                  'crystal plaza': {'_meta': {'name': 'Crystal plaza South',
                                                              'population': 681}},
                                  'loft': {'_meta': {'name': 'loft hotel',
                                                     'population': 216}},
                                  'riverhouse': {'_meta': {'name': 'RiverHouse 1400',
                                                           'population': 437}}},
                    'vienna': {'_meta': {'name': 'vienna county', 'population': 1500}}},
             '_meta': {'_rootname': 'US', 'population': 27800000.0}}
        """
        if kwarg:
            d[key] = {_meta: kwarg}
        else:
            d[key] = dict()

    @staticmethod
    def ac(d, key, **kwarg):
        """Alias of :meth:`self.add_children()<DictTree.add_children>`.
        """
        if kwarg:
            d[key] = {_meta: kwarg}
        else:
            d[key] = dict()
            
    @staticmethod
    def k(d):
        """Equivalent to dict.keys().
        Usage reference see :meth:`DictTree.kv()<DictTree.kv>`
        """
        return (key for key in iterkeys(d) if key != _meta)

    @staticmethod
    def v(d):
        """Equivalent to dict.values().
        Usage reference see :meth:`DictTree.kv()<DictTree.kv>`
        """
        return (value for key, value in iteritems(d) if key != _meta)

    @staticmethod
    def kv(d):
        """Equivalent to dict.items().
        
        Usage::
        
            >>> for key, node in DictTree.kv(d):
            >>>     print(key, DictTree.getattr(node, "population"))  
            MD 200000
            VA 100000
        """
        return ((key, value) for key, value in iteritems(d) if key != _meta)

    @staticmethod
    def k_depth(d, depth, _counter=1):
        """Iterate keys on specific depth.
        depth has to be greater equal than 0. 
        Usage reference see :meth:`DictTree.kv_depth()<DictTree.kv_depth>`
        """
        if depth == 0:
            yield d[_meta]["_rootname"]
        else:
            if _counter == depth:
                for key in DictTree.k(d):
                    yield key
            else:
                _counter += 1
                for node in DictTree.v(d):
                    for key in DictTree.k_depth(node, depth, _counter):
                        yield key

    @staticmethod
    def v_depth(d, depth):
        """Iterate values on specific depth.
        depth has to be greater equal than 0.
        Usage reference see :meth:`DictTree.kv_depth()<DictTree.kv_depth>`
        """
        if depth == 0:
            yield d
        else:
            for node in DictTree.v(d):
                for node1 in DictTree.v_depth(node, depth-1):
                    yield node1

    @staticmethod
    def kv_depth(d, depth, _counter=1):
        """Iterate items on specific depth.
        depth has to be greater equal than 0.
    
        Usage::
            
            >>> for key, node in DictTree.kv_depth(d, 2):
            >>>     print(key, DictTree.getattr(node, "population"))   
            bethesta 5800
            germentown 1400
            vienna 1500
            arlington 5000
        """
        if depth == 0:
            yield d[_meta]["_rootname"], d
        else:
            if _counter == depth:
                for key, node in DictTree.kv(d):
                    yield key, node
            else:
                _counter += 1
                for node in DictTree.v(d):
                    for key, node in DictTree.kv_depth(node, depth, _counter):
                        yield key, node

    @staticmethod   
    def length(d):
        """Get the number of immediate child nodes.
        """
        if _meta in d:
            return len(d) - 1
        else:
            return len(d)
    
    @staticmethod
    def len_on_depth(d, depth):
        """Get the number of nodes on specific depth.
        """
        counter = 0
        for node in DictTree.v_depth(d, depth-1):
            counter += DictTree.length(node)
        return counter
    
    @staticmethod
    def copy(d):
        """Copy current dict.
        Because members in this dicttree are also dict, which is mutable.
        so we have to use deepcopy to avoid mistake.
        """
        return copy.deepcopy(d)
    
    @staticmethod
    def del_depth(d, depth):
        """Delete all the nodes on specific depth in this dict
        """
        for node in DictTree.v_depth(d, depth-1):
            for key in [key for key in DictTree.k(node)]:
                del node[key]

    @staticmethod
    def prettyprint(d):
        """Print dicttree in Json-like format. keys are sorted
        """
        print(json.dumps(d, sort_keys=True, 
                         indent=4, separators=("," , ": ")))

    @staticmethod
    def stats_on_depth(d, depth):
        """Display the node stats info on specific depth in this dict
        """
        root_nodes, leaf_nodes = 0, 0
        for _, node in DictTree.kv_depth(d, depth):
            if DictTree.length(node) == 0:
                leaf_nodes += 1
            else:
                root_nodes += 1
        total = root_nodes + leaf_nodes
        print("On depth %s, having %s root nodes, %s leaf nodes. "
              "%s nodes in total." % (depth, root_nodes, leaf_nodes, total))


#--- Unittest ---
if __name__ == "__main__":
    from pprint import pprint as ppt
    import unittest
    
    d = DictTree.initial("US")
    DictTree.setattr(d, population=27.8*1000*1000)
    DictTree.add_children(d, "VA", 
                          name="virginia", population=100*1000)
    DictTree.add_children(d, "MD", 
                          name="maryland", population=200*1000)
    
    DictTree.add_children(d["VA"], "arlington", 
                          name="arlington county", population=5000)
    DictTree.add_children(d["VA"], "vienna", 
                          name="vienna county", population=1500)
    DictTree.add_children(d["MD"], "bethesta", 
                          name="montgomery country", population=5800)
    DictTree.add_children(d["MD"], "germentown", 
                          name="fredrick country", population=1400)
     
    DictTree.add_children(d["VA"]["arlington"], "riverhouse", 
                          name="RiverHouse 1400", population=437)
    DictTree.add_children(d["VA"]["arlington"], "crystal plaza", 
                          name="Crystal plaza South", population=681)
    DictTree.add_children(d["VA"]["arlington"], "loft", 
                          name="loft hotel", population=216)
    
    ppt(d)
    
    class DictTreeUnittest(unittest.TestCase):
        def test_iter_method(self):
            self.assertSetEqual(set(DictTree.k(d)), set(["VA", "MD"]))
         
        def test_iter_on_depth_method(self):
            self.assertSetEqual(set(DictTree.k_depth(d, 0)), set(["US"]))
            self.assertSetEqual(set(DictTree.k_depth(d, 1)), set(["VA", "MD"]))
            self.assertSetEqual(set(DictTree.k_depth(d, 2)), 
                                set(["arlington", "vienna", 
                                     "bethesta", "germentown"]))
            self.assertSetEqual(set(DictTree.k_depth(d, 3)), 
                                set(["riverhouse", "crystal plaza", "loft"]))
             
        def test_length_method(self):
            self.assertEqual(DictTree.length(d), 2)
            self.assertEqual(DictTree.length(d["VA"]), 2)
            self.assertEqual(DictTree.length(d["MD"]), 2)
            self.assertEqual(DictTree.length(d["VA"]["arlington"]), 3)
            self.assertEqual(DictTree.length(d["MD"]["bethesta"]), 0)
            self.assertEqual(DictTree.len_on_depth(d, 0), 0)
            self.assertEqual(DictTree.len_on_depth(d, 1), 2)
            self.assertEqual(DictTree.len_on_depth(d, 2), 4)
            self.assertEqual(DictTree.len_on_depth(d, 3), 3)
            self.assertEqual(DictTree.len_on_depth(d, 4), 0)
        
        def test_del_depth(self):
            d1 = copy.deepcopy(d)
            DictTree.del_depth(d1, 2)
            self.assertEqual(DictTree.len_on_depth(d1, 1), 2)
            self.assertEqual(DictTree.len_on_depth(d1, 2), 0)
            self.assertEqual(DictTree.len_on_depth(d1, 3), 0)
            
        def test_status_on_depth(self):
            DictTree.stats_on_depth(d, 0)
            DictTree.stats_on_depth(d, 1)
            DictTree.stats_on_depth(d, 2)
            DictTree.stats_on_depth(d, 3)
            DictTree.stats_on_depth(d, 4)
             
    unittest.main()