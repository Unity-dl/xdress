"""This module creates descriptions of C/C++ classes, functions, and variables 
from source code, by using external parsers (GCC-XML, Clang AST) and the type system.

This module is available as an xdress plugin by the name ``xdress.autodescribe``.

:author: Anthony Scopatz <scopatz@gmail.com>

Descriptions
============
A key component of API wrapper generation is having a a top-level, abstract 
representation of the software that is being wrapped.  In C++ there are three
basic constructs which may be wrapped: variables, functions, and classes.  

The abstract representation of a C++ class is known as a **description** (abbr. 
*desc*).  This description is simply a Python dictionary with a specific structure.
This structure makes heavy use of the type system to declare the types of all needed
parameters.

Variable Description Top-Level Keys
------------------------------------
The following are valid top-level keys in a variable description dictionary: 
name, namespace, type, docstring, and extra.

:name: str, the variable name
:namespace: str or None, the namespace or module the variable lives in.
:type: str or tuple, the type of the variable
:docstring: str, optional, this is a documentation string for the variable.  
:extra: dict, optional, this stores arbitrary metadata that may be used with 
    different backends. It is not added by any auto-describe routine but may be
    inserted later if needed.  One example use case is that the Cython generation
    looks for the pyx, pxd, and cpppxd keys for strings of supplemental Cython 
    code to insert directly into the wrapper.

Function Description Top-Level Keys
------------------------------------
The following are valid top-level keys in a function description dictionary: 
name, namespace, signatures, docstring, and extra.

:name: str, the function name
:namespace: str or None, the namespace or module the function lives in.
:signatures: dict or dict-like, the keys of this dictionary are function call 
    signatures and the values are the function return types. The signatures
    themselves are tuples. The first element of these tuples is the function name.
    The remaining elements (if any) are the function arguments.  Arguments are 
    themselves length-2 or -3 tuples whose first elements are the argument names, 
    the second element is the argument type, and the third element (if present) is
    the default value. Unlike class constuctors and destructors, the return type may 
    not be None (only 'void' values are allowed).
:docstring: str, optional, this is a documentation string for the function.  
:extra: dict, optional, this stores arbitrary metadata that may be used with 
    different backends. It is not added by any auto-describe routine but may be
    inserted later if needed.  One example use case is that the Cython generation
    looks for the pyx, pxd, and cpppxd keys for strings of supplemental Cython 
    code to insert directly into the wrapper.

Class Description Top-Level Keys
---------------------------------
The following are valid top-level keys in a class description dictionary: 
name, parents, namespace, attrs, methods, docstrings, and extra.

:name: str, the class name
:parents: list of strings or None, the immediate parents of the class
    (not grandparents).
:namespace: str or None, the namespace or module the class lives in.
:attrs: dict or dict-like, the names of the attributes (member variables) of the
    class mapped to their types, given in the format of the type system.
:methods: dict or dict-like, similar to the attrs except that the keys are now
    function signatures and the values are the method return types.  The signatures
    themselves are tuples. The first element of these tuples is the method name.
    The remaining elements (if any) are the function arguments.  Arguments are 
    themselves length-2 or -3 tuples whose first elements are the argument names, 
    the second element is the argument type, and the third element (if present) is
    the default value.  If the return type is None (as opposed to 'void'), then 
    this method is assumed to be a constructor or destructor.
:construct: str, optional, this is a flag for how the class is implemented. 
    Accepted values are 'class' and 'struct'.  If this is not present, then 'class'
    is assumed.  This is most useful from wrapping C structs as Python classes.
:docstrings: dict, optional, this dictionary is meant for storing documentation 
    strings.  All values are thus either strings or dictionaries of strings.  
    Valid keys include: class, attrs, and methods.  The attrs and methods
    keys are dictionaries which may include keys that mirror the top-level keys of
    the same name.
:extra: dict, optional, this stores arbitrary metadata that may be used with 
    different backends. It is not added by any auto-describe routine but may be
    inserted later if needed.  One example use case is that the Cython generation
    looks for the pyx, pxd, and cpppxd keys for strings of supplemental Cython 
    code to insert directly into the wrapper.

Toaster Example
---------------
Suppose we have a C++ class called Toaster that takes bread and makes delicious 
toast.  A valid description dictionary for this class would be as follows::

    class_desc = {
        'name': 'Toaster',
        'parents': ['FCComp'],
        'namespace': 'bright',
        'attrs': {
            'n_slices': 'int32',
            'rate': 'float64',
            'toastiness': 'str',
            },
        'methods': {
            ('Toaster',): None,
            ('Toaster', ('name', 'str', '""')): None,
            ('Toaster', ('paramtrack', ('set', 'str')), ('name', 'str', '""')): None,
            ('~Toaster',): None, 
            ('tostring',): 'str', 
            ('calc',): 'Material',
            ('calc', ('incomp', ('map', 'int32', 'float64'))): 'Material',
            ('calc', ('mat', 'Material')): 'Material',
            ('write', ('filename', 'str', '"toaster.txt"')): 'void',
            ('write', ('filename', ('char' '*'), '"toaster.txt"')): 'void',
            },
        'docstrings': {
            'class': "I am a toaster!",
            'attrs': {
                'n_slices': 'the number of slices',
                'rate': 'the toast rate',
                'toastiness': 'the toastiness level',
                },
            'methods': {
                'Toaster': "Make me a toaster!",
                '~Toaster': "Noooooo",
                'tostring': "string representation of the toaster",
                'calc': "actually makes the toast.",
                'write': "persists the toaster state."
                },
            },
        'extra': {
            'pyx': 'toaster = Toaster()  # make toaster singleton'
            },
        }

Automatic Description Generation
--------------------------------
The purpose of this module is to create description dictionaries like those
above by automatically parsing C++ classes.  In theory this parsing step may 
be handled by visiting any syntax tree of C++ code.  Two options were pursued here:
GCC-XML and the Python bindings to the Clang AST.  Unfortunately, the Clang AST
bindings lack exposure for template argument types.  These are needed to use any
standard library containers.  Thus while the Clang method was pursued to a mostly
working state, the GCC-XML version is the only fully functional automatic describer
for the moment.

Automatic Descriptions API
==========================
"""
from __future__ import print_function
import os
import io
import sys
from copy import deepcopy
import linecache
import subprocess
import itertools
import functools
import pickle
import collections
from pprint import pprint, pformat
from warnings import warn

if os.name == 'nt':
    import ntpath
    import posixpath

# pycparser conditional imports
try:
    import pycparser
    PycparserNodeVisitor = pycparser.c_ast.NodeVisitor
except ImportError:
    pycparser = None
    PycparserNodeVisitor = object  # fake this for class definitions

from . import utils
from .utils import exec_file, RunControl, NotSpecified, merge_descriptions, \
    find_source, FORBIDDEN_NAMES
from . import astparsers

from . import typesystem as ts

if sys.version_info[0] >= 3: 
    basestring = str

def clearmemo():
    """Clears all function memoizations for autodescribers."""
    for x in globals().values():
        if callable(x) and hasattr(x, 'cache'):
            x.cache.clear()

#
# GCC-XML Describers
#

def gccxml_describe(filename, name, kind, includes=(), defines=('XDRESS',), 
                    undefines=(), verbose=False, debug=False, builddir='build'):
    """Use GCC-XML to describe the class.

    Parameters
    ----------
    filename : str
        The path to the file.
    name : str or None, optional
        The name, a 'None' value will attempt to infer this from the 
        filename.
    kind : str
        The kind of type to describe, valid flags are 'class', 'func', and 'var'.
    includes: list of str, optional
        The list of extra include directories to search for header files.
    defines: list of str, optional
        The list of extra macro definitions to apply.
    undefines: list of str, optional
        The list of extra macro undefinitions to apply.
    verbose : bool, optional
        Flag to diplay extra information while describing the class.
    debug : bool, optional
        Flag to enable/disable debug mode.
    builddir : str, optional
        Location of -- often temporary -- build files.

    Returns
    -------
    desc : dict
        A dictionary describing the class which may be used to generate
        API bindings.
    """
    if os.name == 'nt':
        # GCC-XML and/or Cygwin wants posix paths on Windows.
        filename = posixpath.join(*ntpath.split(filename)) 
    root = astparsers.gccxml_parse(filename, includes=includes, defines=defines, 
                                   undefines=undefines, verbose=verbose, debug=debug, 
                                   builddir=builddir)
    basename = filename.rsplit('.', 1)[0]
    onlyin = set([filename] +
                 [basename + '.' + h for h in utils._hdr_exts if h.startswith('h')])
    describers = {'class': GccxmlClassDescriber, 'func': GccxmlFuncDescriber, 
                  'var': GccxmlVarDescriber}
    describer = describers[kind](name, root, onlyin=onlyin, verbose=verbose)
    describer.visit()
    return describer.desc


class GccxmlBaseDescriber(object):
    """Base class used to generate descriptions via GCC-XML output.
    Sub-classes need only implement a visit() method and optionally a 
    constructor.  The default visitor methods are valid for classes."""

    _funckey = None
    _integer_types = frozenset(['int32', 'int64', 'uint32', 'uint64'])

    def __init__(self, name, root=None, onlyin=None, verbose=False):
        """Parameters
        -------------
        name : str
            The name, this may not have a None value.
        root : element tree node, optional
            The root element node.  
        onlyin :  str, optional
            Filename the class or struct described must live in.  Prevents 
            finding elements of the same name coming from other libraries.
        verbose : bool, optional
            Flag to display extra information while visiting.

        """
        self.desc = {'name': name}
        self.name = name
        self.verbose = verbose
        self._root = root
        origonlyin = onlyin
        onlyin = [onlyin] if isinstance(onlyin, basestring) else onlyin
        onlyin = set() if onlyin is None else set(onlyin)
        onlyin = [root.find("File[@name='{0}']".format(oi)) for oi in onlyin]
        self.onlyin = set([oi.attrib['id'] for oi in onlyin if oi is not None])
        if 0 == len(self.onlyin):
            msg = "{0!r} is not present in {1!r}; autodescribing will probably fail."
            msg = msg.format(name, origonlyin)
            warn(msg, RuntimeWarning)
        self._currfunc = []  # this must be a stack to handle nested functions
        self._currfuncsig = None
        self._currclass = []  # this must be a stack to handle nested classes  
        self._level = -1

    def __str__(self):
        return pformat(self.desc)

    def __del__(self):
        linecache.clearcache()

    def _pprint(self, node):
        if self.verbose:
            print("{0}{1} {2}: {3}".format(self._level * "  ", node.tag,
                                       node.attrib.get('id', ''),
                                       node.attrib.get('name', None)))

    _template_args = {
        'array': ('value_type',),
        'deque': ('value_type',),
        'forward_list': ('value_type',),
        'list': ('value_type',),
        'map': ('key_type', 'mapped_type'),
        'multimap': ('key_type', 'mapped_type'),
        'set': ('key_type',),
        'multiset': ('key_type',),
        'unordered_map': ('key_type', 'mapped_type'),
        'unordered_multimap': ('key_type', 'mapped_type'),
        'unordered_set': ('key_type',),
        'unordered_multiset': ('key_type',),
        'vector': ('value_type',),
        }

    def _visit_template(self, node):
        name = node.attrib['name']
        members = node.attrib.get('members', '').strip().split()
        children = [child for m in members for child in \
                                self._root.iterfind(".//*[@id='{0}']".format(m))]
        tags = [child.tag for child in children]
        template_name = children[tags.index('Constructor')].attrib['name']  # 'map'
        if template_name == 'basic_string':
            return 'str'
        inst = [template_name]
        self._level += 1
        if template_name in self._template_args:
            for targ in self._template_args[template_name]:
                targ_nodes = [c for c in children if c.attrib['name'] == targ]
                targ_node = targ_nodes[0]
                targ_type = self.type(targ_node.attrib['id'])
                inst.append(targ_type)
        else:
            # fill in later with string parsing of node name if needed.
            pass
        self._level -= 1
        #inst.append(0)
        return tuple(inst)

    def visit_class(self, node):
        """visits a class or struct."""
        self._pprint(node)
        name = node.attrib['name']
        self._currclass.append(name)
        if name == self.name:
            bases = node.attrib['bases'].split()
            bases = None if len(bases) == 0 else [self.type(b) for b in bases]
            self.desc['parents'] = bases
            ns = self.context(node.attrib['context'])
            if ns is not None:
                self.desc['namespace'] = ns
        if '<' in name and name.endswith('>'):
            name = self._visit_template(node)
        self._currclass.pop()
        return name

    visit_struct = visit_class

    def visit_base(self, node):
        """visits a base class."""
        self._pprint(node)
        self.visit(node)  # Walk farther down the tree

    def _visit_func(self, node):
        name = node.attrib['name']
        if name.startswith('_') or name in FORBIDDEN_NAMES:
            return
        self._currfunc.append(name)
        self._currfuncsig = []
        self._level += 1
        for child in node.iterfind('Argument'):
            self.visit_argument(child)
        self._level -= 1
        if node.tag == 'Constructor':
            rtntype = None
        elif node.tag == 'Destructor':
            rtntype = None
            self._currfunc[-1] = '~' + self._currfunc[-1]
        else: 
            rtntype = self.type(node.attrib['returns'])
        funcname = self._currfunc.pop()
        if self._currfuncsig is None:
            return 
        key = (funcname,) + tuple(self._currfuncsig)
        self.desc[self._funckey][key] = rtntype
        self._currfuncsig = None

    def visit_constructor(self, node):
        """visits a class constructor."""
        self._pprint(node)
        self._visit_func(node)

    def visit_destructor(self, node):
        """visits a class destructor."""
        self._pprint(node)
        self._visit_func(node)

    def visit_method(self, node):
        """visits a member function."""
        self._pprint(node)
        self._visit_func(node)

    def visit_function(self, node):
        """visits a non-member function."""
        self._pprint(node)
        self._visit_func(node)
        ns = self.context(node.attrib['context'])
        if ns is not None:
            self.desc['namespace'] = ns

    def visit_argument(self, node):
        """visits a constructor, destructor, or method argument."""
        self._pprint(node)
        name = node.attrib.get('name', None)
        if name is None or name in FORBIDDEN_NAMES:
            self._currfuncsig = None
            return 
        tid = node.attrib['type']
        t = self.type(tid)
        default = node.attrib.get('default', None)
        if default is None:
            arg = (name, t)
        else:
            if t in self._integer_types:
                default = int(default)
            arg = (name, t, default)
        self._currfuncsig.append(arg)

    def visit_field(self, node):
        """visits a member variable."""
        self._pprint(node)
        context = self._root.find(".//*[@id='{0}']".format(node.attrib['context']))
        if context.attrib['name'] == self.name:
            # assert this field is member of the class we are trying to parse
            name = node.attrib['name']
            if name in FORBIDDEN_NAMES:
                return 
            t = self.type(node.attrib['type'])
            self.desc['attrs'][name] = t

    def visit_typedef(self, node):
        """visits a type definition anywhere."""
        self._pprint(node)
        name = node.attrib.get('name', None)
        if name == 'string':
            return 'str'
        else:
            return self.type(node.attrib['type'])

    _fundemntal_to_base = {
        'char': 'char', 
        'int': 'int32', 
        'long int': 'int64', 
        'unsigned int': 'uint32',
        'long unsigned int': 'uint64',
        'float': 'float32',
        'double': 'float64',
        'complex': 'complex128', 
        'void': 'void', 
        'bool': 'bool',
        }

    def visit_fundamentaltype(self, node):
        """visits a base C++ type, mapping it to the approriate type in the 
        type system."""
        self._pprint(node)
        tname = node.attrib['name']
        t = self._fundemntal_to_base.get(tname, None)
        return t

    _predicates = frozenset(['*', '&', 'const', 'volatile', 'restrict'])

    def _add_predicate(self, baset, pred):
        if isinstance(baset, basestring):
            return (baset, pred)
        last = baset[-1]
        if last in self._predicates or isinstance(last, int):
            return (baset, pred)
        else:
            return tuple(baset) + (pred,)

    def visit_arraytype(self, node):
        """visits an array type and maps it to a '*' refinement type."""
        self._pprint(node)
        baset = self.type(node.attrib['type'])
        # FIXME something involving the min, max, and/or size 
        # attribs needs to also go here.
        t = self._add_predicate(baset, '*')
        return t

    def visit_referencetype(self, node):
        """visits a refernece and maps it to a '&' refinement type."""
        self._pprint(node)
        baset = self.type(node.attrib['type'])
        t = self._add_predicate(baset, '&')
        return t

    def visit_pointertype(self, node):
        """visits a pointer and maps it to a '*' refinement type."""
        self._pprint(node)
        baset = self.type(node.attrib['type'])
        t = self._add_predicate(baset, '*')
        return t

    def visit_cvqualifiedtype(self, node):
        """visits constant, volatile, and restricted types and maps them to 
        'const', 'volatile', and 'restrict' refinement types."""
        self._pprint(node)
        t = self.type(node.attrib['type'])
        if int(node.attrib.get('const', 0)):
            t = self._add_predicate(t, 'const')
        if int(node.attrib.get('volatile', 0)):
            t = self._add_predicate(t, 'volatile')
        if int(node.attrib.get('restrict', 0)):
            t = self._add_predicate(t, 'restrict')
        return t

    def type(self, id):
        """Resolves the type from its id and information in the root element tree."""
        node = self._root.find(".//*[@id='{0}']".format(id))
        tag = node.tag.lower()
        meth_name = 'visit_' + tag
        meth = getattr(self, meth_name, None)
        t = None
        if meth is not None:
            self._level += 1
            t = meth(node)
            self._level -= 1
        return t

    def visit_namespace(self, node):
        """visits the namespace that a node is defined in."""
        self._pprint(node)
        name = node.attrib['name']
        return name

    def context(self, id):
        """Resolves the context from its id and information in the element tree."""
        node = self._root.find(".//*[@id='{0}']".format(id))
        tag = node.tag.lower()
        meth_name = 'visit_' + tag
        meth = getattr(self, meth_name, None)
        c = None
        if meth is not None:
            self._level += 1
            c = meth(node)
            self._level -= 1
        return c


class GccxmlClassDescriber(GccxmlBaseDescriber):
    """Class used to generate class descriptions via GCC-XML output."""

    _funckey = 'methods'
    _constructvalue = 'class'

    def __init__(self, name, root=None, onlyin=None, verbose=False):
        """Parameters
        -------------
        name : str
            The class name, this may not have a None value.
        root : element tree node, optional
            The root element node of the class or struct to describe.  
        onlyin :  str, optional
            Filename the class or struct described must live in.  Prevents 
            finding classes of the same name coming from other libraries.
        verbose : bool, optional
            Flag to display extra information while visiting the class.

        """
        super(GccxmlClassDescriber, self).__init__(name, root=root, onlyin=onlyin, 
                                                   verbose=verbose)
        self.desc['attrs'] = {}
        self.desc[self._funckey] = {}
        self.desc['construct'] = self._constructvalue

    def visit(self, node=None):
        """Visits the class node and all sub-nodes, generating the description
        dictionary as it goes.

        Parameters
        ----------
        node : element tree node, optional
            The element tree node to start from.  If this is None, then the 
            top-level class node is found and visited.

        """
        if node is None:
            node = self._root.find("Class[@name='{0}']".format(self.name))
            if node is None:
                node = self._root.find("Struct[@name='{0}']".format(self.name))
            if node.attrib['file'] not in self.onlyin:
                msg = ("{0} autodescribing failed: found class in {1!r} but "
                       "expected it in {2!r}.")
                msg = msg.format(self.name, node.attrib['file'], self.onlyin)
                raise RuntimeError(msg)
            self.visit_class(node)
        members = node.attrib.get('members', '').strip().split()
        children = [self._root.find(".//*[@id='{0}']".format(m)) for m in members]
        children = [c for c in children if c.attrib['access'] == 'public']
        self._level += 1
        for child in children:
            tag = child.tag.lower()
            meth_name = 'visit_' + tag
            meth = getattr(self, meth_name, None)
            if meth is not None:
                meth(child)
        self._level -= 1

class GccxmlVarDescriber(GccxmlBaseDescriber):
    """Class used to generate variable descriptions via GCC-XML output."""

    def __init__(self, name, root=None, onlyin=None, verbose=False):
        """Parameters
        -------------
        name : str
            The function name, this may not have a None value.
        root : element tree node, optional
            The root element node of the function to describe.  
        onlyin :  str, optional
            Filename the function described must live in.  Prevents finding 
            functions of the same name coming from other libraries.
        verbose : bool, optional
            Flag to display extra information while visiting the function.

        """
        super(GccxmlVarDescriber, self).__init__(name, root=root, onlyin=onlyin, 
                                                 verbose=verbose)

    def visit(self, node=None):
        """Visits the variable node and all sub-nodes, generating the description
        dictionary as it goes.

        Parameters
        ----------
        node : element tree node, optional
            The element tree node to start from.  If this is None, then the 
            top-level class node is found and visited.

        """
        root = node or self._root
        for n in root.iterfind("Variable[@name='{0}']".format(self.name)):
            if n.attrib['file'] in self.onlyin:
                ns = self.context(n.attrib['context'])
                if ns is not None:
                    self.desc['namespace'] = ns
                self.desc['type'] = self.type(n.attrib['type'])
                break
            else:
                msg = ("{0} autodescribing failed: found variable in {1!r} but "
                       "expected it in {2!r}.")
                msg = msg.format(self.name, node.attrib['file'], self.onlyin)
                raise RuntimeError(msg)

class GccxmlFuncDescriber(GccxmlBaseDescriber):
    """Class used to generate function descriptions via GCC-XML output."""

    _funckey = 'signatures'

    def __init__(self, name, root=None, onlyin=None, verbose=False):
        """Parameters
        -------------
        name : str
            The function name, this may not have a None value.
        root : element tree node, optional
            The root element node of the function to describe.  
        onlyin :  str, optional
            Filename the function described must live in.  Prevents finding 
            functions of the same name coming from other libraries.
        verbose : bool, optional
            Flag to display extra information while visiting the function.

        """
        super(GccxmlFuncDescriber, self).__init__(name, root=root, onlyin=onlyin, 
                                                   verbose=verbose)
        self.desc[self._funckey] = {}

    def visit(self, node=None):
        """Visits the function node and all sub-nodes, generating the description
        dictionary as it goes.

        Parameters
        ----------
        node : element tree node, optional
            The element tree node to start from.  If this is None, then the 
            top-level class node is found and visited.

        """
        root = node or self._root
        for n in root.iterfind("Function[@name='{0}']".format(self.name)):
            if n.attrib['file'] in self.onlyin:
                self.visit_function(n)
            else:
                msg = ("{0} autodescribing failed: found function in {1!r} but "
                       "expected it in {2!r}.")
                msg = msg.format(self.name, node.attrib['file'], self.onlyin)
                raise RuntimeError(msg)
#
# Clang Describers
#

@astparsers.not_implemented
def clang_describe(filename, name, includes=(), defines=('XDRESS',),
                   undefines=(), verbose=False, debug=False, builddir='build'):
    "Use clang to describe the class."
    index = cindex.Index.create()
    tu = index.parse(filename, args=['-cc1', '-I' + pyne.includes, '-D', 'XDRESS'])
    #onlyin = set([filename, filename.replace('.cpp', '.h')])
    onlyin = set([filename.replace('.cpp', '.h')])
    describer = ClangClassDescriber(name, onlyin=onlyin, verbose=verbose)
    describer.visit(tu.cursor)
    pprint(describer.desc)
    return describer.desc


@astparsers.not_implemented
def clang_is_loc_in_range(location, source_range):
    """Returns whether a given Clang location is part of a source file range."""
    if source_range is None or location is None:
        return False
    start = source_range.start
    stop = source_range.end
    file = location.file
    if file != start.file or file != stop.file:
        return False
    line = location.line
    if line < start.line or stop.line < line:
        return False
    return start.column <= location.column <= stop.column


@astparsers.not_implemented
def clang_range_str(source_range):
    """Get the text present on a source range."""
    start = source_range.start
    stop = source_range.end
    filename = start.file.name
    if filename != stop.file.name:
        msg = 'range spans multiple files: {0!r} & {1!r}'
        msg = msg.format(filename, stop.file.name)
        raise ValueError(msg)
    lines = [linecache.getline(filename, n) for n in range(start.line, stop.line+1)]
    lines[-1] = lines[-1][:stop.column-1]  # stop slice must come first for 
    lines[0] = lines[0][start.column-1:]   # len(lines) == 1
    s = "".join(lines)
    return s
    


@astparsers.not_implemented
class ClangClassDescriber(object):

    _funckinds = set(['function_decl', 'cxx_method', 'constructor', 'destructor'])

    def __init__(self, name, root=None, onlyin=None, verbose=False):
        self.desc = {'name': name, 'attrs': {}, 'methods': {}}
        self.name = name
        self.verbose = verbose
        onlyin = [onlyin] if isinstance(onlyin, basestring) else onlyin
        self.onlyin = set() if onlyin is None else set(onlyin)
        self._currfunc = []  # this must be a stack to handle nested functions
        self._currfuncsig = None
        self._currfuncarg = None
        self._currclass = []  # this must be a stack to handle nested classes  

    def __str__(self):
        return pformat(self.desc)

    def __del__(self):
        linecache.clearcache()

    def _pprint(self, node, typename):
        if self.verbose:
            print("{0}: {1}".format(typename, node.displayname))

    def visit(self, root):
        for node in root.get_children():
            if not node.location.file or node.location.file.name not in self.onlyin:
                continue  # Ignore AST elements not from the desired source files
            kind = node.kind.name.lower()
            meth_name = 'visit_' + kind
            meth = getattr(self, meth_name, None)
            if meth is not None:
                meth(node)
            if hasattr(node, 'get_children'):
                self.visit(node)

            # reset the current function and class
            if kind in self._funckinds and node.spelling == self._currfunc[-1]:
                _key, _value = self._currfuncsig
                _key = (_key[0],) + tuple([tuple(k) for k in _key[1:]])
                self.desc['methods'][_key] = _value
                self._currfunc.pop()
                self._currfuncsig = None
            elif 'class_decl' == kind and node.spelling == self._currclass[-1]:
                self._currclass.pop()
            elif 'unexposed_expr' == kind and node.spelling == self._currfuncarg:
                self._currfuncarg = None

    def visit_class_decl(self, node):
        self._pprint(node, "Class")
        self._currclass.append(node.spelling)  # This could also be node.displayname

    def visit_function_decl(self, node):
        self._pprint(node, "Function")
        self._currfunc.append(node.spelling)  # This could also be node.displayname
        rtntype = node.type.get_result()
        rtnname = ClangTypeVisitor(verbose=self.verbose).visit(rtntype)
        self._currfuncsig = ([node.spelling], rtnname)

    visit_cxx_method = visit_function_decl

    def visit_constructor(self, node):
        self._pprint(node, "Constructor")
        self._currfunc.append(node.spelling)  # This could also be node.displayname
        self._currfuncsig = ([node.spelling], None)

    def visit_destructor(self, node):
        self._pprint(node, "Destructor")
        self._currfunc.append(node.spelling)  # This could also be node.displayname
        self._currfuncsig = ([node.spelling], None)

    def visit_parm_decl(self, node):
        self._pprint(node, "Function Argument")
        name = node.spelling
        t = ClangTypeVisitor(verbose=self.verbose).visit(node)
        self._currfuncsig[0].append([name, t])
        self._currfuncarg = name

    def visit_field_decl(self, node):
        self._pprint(node, "Field")

    def visit_var_decl(self, node):
        self._pprint(node, "Variable")

    def visit_unexposed_expr(self, node):
        self._pprint(node, "Default Parameter (Unexposed Expression)")
        # a little hacky reading from the file, 
        # but Clang doesn't expose this data...
        if self._currfuncsig is None:
            return
        currarg = self._currfuncsig[0][-1]
        assert currarg[0] == self._currfuncarg
        r = node.extent
        default_val = clang_range_str(r)
        if 2 == len(currarg):
            currarg.append(default_val)
        elif 3 == len(currarg):
            currarg[2] = default_val

    ##########

    def visit_type_ref(self, cur):
        self._pprint(cur, "type ref")

    def visit_template_ref(self, cur):
        self._pprint(cur, "template ref")

    def visit_template_type_parameter(self, cur):
        self._pprint(cur, "template type param")

    def visit_template_non_type_parameter(self, cur):
        self._pprint(cur, "template non-type param")

    def visit_template_template_parameter(self, cur):
        self._pprint(cur, "template template param")

    def visit_class_template(self, cur):
        self._pprint(cur, "class template")

    def visit_class_template_partial_specialization(self, cur):
        self._pprint(cur, "class template partial specialization")


@astparsers.not_implemented
def clang_find_class(node, name, namespace=None):
    """Find the node for a given class underneath the current node.
    """
    if namespace is None:
        nsdecls = [node]
    else:
        nsdecls = [n for n in clang_find_declarations(node) if n.spelling == namespace]
    classnode = None
    for nsnode in nsdecls[::-1]:
        decls = [n for n in clang_find_declarations(nsnode) if n.spelling == name]
        if 0 < len(decls):
            assert 1 == len(decls)
            classnode = decls[0]
            break
    if classnode is None:
        msg = "the class {0} could not be found in {1}".format(name, filename)
        raise ValueError(msg)
    return classnode


@astparsers.not_implemented
def clang_find_declarations(node):
    """Finds declarations one level below the Clang node."""
    return [n for n in node.get_children() if n.kind.is_declaration()]

@astparsers.not_implemented
def clang_find_attributes(node):
    """Finds attributes one level below the Clang node."""
    return [n for n in node.get_children() if n.kind.is_attribute()]


@astparsers.not_implemented
class ClangTypeVisitor(object):
    """For a Clang type located at a root node, compute the cooresponding 
    typesystem type.
    """

    def __init__(self, verbose=False):
        self.type = []
        self.verbose = verbose
        self.namespace = []  # this must be a stack to handle nested namespaces
        self._atrootlevel = True
        self._currtype = []

    def _pprint(self, node, typename):
        if self.verbose:
            msg = "{0}: {1}"
            if isinstance(node, cindex.Type):
                msg = msg.format(typename, node.kind.spelling)
            elif isinstance(node, cindex.Cursor):
                msg = msg.format(typename, node.displayname)
            else:
                msg = msg.format(typename, node)
            print(msg)

    def visit(self, root):
        """Takes a root type."""
        atrootlevel = self._atrootlevel

        if isinstance(root, cindex.Type):
            typekind = root.kind.name.lower()
            methname = 'visit_' + typekind
            meth = getattr(self, methname, None)
            if meth is not None and root.kind != cindex.TypeKind.INVALID:
                meth(root)
        elif isinstance(root, cindex.Cursor):
            self.visit(root.type)
            for child in root.get_children():
                kindname = child.kind.name.lower()
                methname = 'visit_' + kindname
                meth = getattr(self, methname, None)
                if meth is not None:
                    meth(child)
                if hasattr(child, 'get_children'):
                    self._atrootlevel = False
                    self.visit(child)
                    self._atrootlevel = atrootlevel
                else:
                    self.visit(child.type)

        if self._atrootlevel:
            currtype = self._currtype
            currtype = currtype[0] if 1 == len(currtype) else tuple(currtype)
            self.type = [self.type, currtype] if isinstance(self.type, basestring) \
                        else list(self.type) + [currtype]
            self._currtype = []
            self.type = self.type[0] if 1 == len(self.type) else tuple(self.type)
            return self.type

    def visit_void(self, typ):
        self._pprint(typ, "void")
        self._currtype.append("void")

    def visit_bool(self, typ):
        self._pprint(typ, "boolean")
        self._currtype.append("bool")

    def visit_char_u(self, typ):
        self._pprint(typ, "character")
        self._currtype.append("char")

    visit_uchar = visit_char_u

    def visit_uint(self, typ):
        self._pprint(typ, "unsigned integer, 32-bit")
        self._currtype.append("uint32")

    def visit_ulong(self, typ):
        self._pprint(typ, "unsigned integer, 64-bit")
        self._currtype.append("uint64")

    def visit_int(self, typ):
        self._pprint(typ, "integer, 32-bit")
        self._currtype.append("int32")

    def visit_long(self, typ):
        self._pprint(typ, "integer, 64-bit")
        self._currtype.append("int64")

    def visit_float(self, typ):
        self._pprint(typ, "float, 32-bit")
        self._currtype.append("float32")

    def visit_double(self, typ):
        self._pprint(typ, "float, 64-bit")
        self._currtype.append("float64")

    def visit_complex(self, typ):
        self._pprint(typ, "complex, 128-bit")
        self._currtype.append("complex128")

    def visit_unexposed(self, typ):
        self._pprint(typ, "unexposed")
        #typ = typ.get_canonical()
        decl = typ.get_declaration()
        self._currtype.append(decl.spelling)
        print("   canon: ",  typ.get_canonical().get_declaration().displayname)
        #import pdb; pdb.set_trace()        
        #self.visit(decl)
        #self.visit(typ.get_canonical().get_declaration())
        #self.visit(typ.get_canonical())

    def visit_typedef(self, typ):
        self._pprint(typ, "typedef")
        decl = typ.get_declaration()
        t = decl.underlying_typedef_type
        #self.visit(t.get_canonical())

    def visit_record(self, typ):
        self._pprint(typ, "record")
        self.visit(typ.get_declaration())

    def visit_invalid(self, typ):
        self._pprint(typ, "invalid")
        self.visit(typ.get_declaration())

    def visit_namespace_ref(self, cur):
        self._pprint(cur, "namespace")
        if self._atrootlevel:
            self.namespace.append(cur.displayname)

    def visit_type_ref(self, cur):
        self._pprint(cur, "type ref")
        self._currtype.append(cur.displayname)
#        print "    cur type kin =", cur.type.kind
        #self.visit(cur.type)
        #self.visit(cur)

    def visit_template_ref(self, cur):
        self._pprint(cur, "template ref")
        self._currtype.append(cur.displayname)
        #self.visit(cur)

        #import pdb; pdb.set_trace()
#        self.visit(cur)
        print("   canon: ",  cur.type.get_canonical().get_declaration().displayname)

    def visit_template_type_parameter(self, cur):
        self._pprint(cur, "template type param")

    def visit_template_non_type_parameter(self, cur):
        self._pprint(cur, "template non-type param")

    def visit_template_template_parameter(self, cur):
        self._pprint(cur, "template template param")

    def visit_function_template(self, cur):
        self._pprint(cur, "function template")

#    def visit_class_template(self, cur):
#        self._pprint(cur, "class template")

    def visit_class_template_partial_specialization(self, cur):
        self._pprint(cur, "class template partial specialization")

#    def visit_var_decl(self, cur):
#        self._pprint(cur, "variable")

@astparsers.not_implemented
def clang_canonize(t):
    kind = t.kind
    if kind in clang_base_typekinds:
        name = clang_base_typekinds[kind]
    elif kind == cindex.TypeKind.UNEXPOSED:
        name = t.get_declaration().spelling
    elif kind == cindex.TypeKind.TYPEDEF:
        print([n.displayname for n in t.get_declaration().get_children()])
        print([n.kind.name for n in t.get_declaration().get_children()])
        name = "<fixme>"
    else:
        name = "<error:{0}>".format(kind)
    return name



#
# pycparser Describers
#


class PycparserBaseDescriber(PycparserNodeVisitor):

    _funckey = None

    def __init__(self, name, root, onlyin=None, verbose=False):
        """Parameters
        -------------
        name : str
            The name, this may not have a None value.
        root : pycparser AST
            The root of the abstract syntax tree.
        onlyin :  str, optional
            Filename the class or struct described must live in.  Prevents 
            finding classes of the same name coming from other libraries.
        verbose : bool, optional
            Flag to display extra information while visiting the class.

        """
        super(PycparserBaseDescriber, self).__init__()
        self.desc = {'name': name, 'namespace': None}
        self.name = name
        self.verbose = verbose
        self._root = root
        self._currfunc = []  # this must be a stack to handle nested functions
        self._currfuncsig = None
        self._currclass = []  # this must be a stack to handle nested classes  
        self._level = -1
        self._currtype = None
        self._currenum = None
        self._loading_bases = False
        self._basetypes = {
            'char': 'char', 
            'signed char': 'char', 
            'unsigned char': 'uchar',
            'short': 'int16',
            'short int': 'int16',
            'signed short': 'int16',
            'signed short int': 'int16',
            'int': 'int32', 
            'signed int': 'int32', 
            'long' : 'int32', 
            'long int' : 'int32', 
            'signed long' : 'int32', 
            'signed long int' : 'int32', 
            'long long' : 'int64', 
            'long long int' : 'int64', 
            'signed long long' : 'int64', 
            'signed long long int' : 'int64', 
            'unsigned short': 'uint16',
            'unsigned short int': 'uint16',
            'unsigned': 'uint32', 
            'unsigned int': 'uint32', 
            'unsigned long': 'uint32',
            'unsigned long int': 'uint32',
            'long unsigned int': 'uint32',
            'unsigned long long' : 'uint64', 
            'unsigned long long int' : 'uint64', 
            'float': 'float32',
            'double': 'float64',
            'long double': 'float128',
            'void': 'void',
            }

    def _pprint(self, node):
        if self.verbose:
            node.show()

    def load_basetypes(self):
        self._loading_bases = True
        for child_name, child in self._root.children():
            if isinstance(child, pycparser.c_ast.Typedef):
                self._basetypes[child.name] = self.type(child)
        if self.verbose:
            print("Base type mapping = ")
            pprint(self._basetypes)
        self._loading_bases = False

    def visit_FuncDef(self, node):
        self._pprint(node)
        name = node.decl.name
        ftype = node.decl.type
        if name.startswith('_') or name in FORBIDDEN_NAMES:
            return
        self._currfunc.append(name)
        self._currfuncsig = []
        self._level += 1
        for _, child in ftype.args.children():
            if isinstance(child, pycparser.c_ast.EllipsisParam):
                continue
            arg = (child.name, self.type(child))
            if arg == (None, 'void'):
                # skip foo(void) cases, since no arg name is given
                continue
            if arg[0] in FORBIDDEN_NAMES:
                return
            self._currfuncsig.append(arg)
        self._level -= 1
        rtntype = self.type(ftype.type)
        funcname = self._currfunc.pop()
        if self._currfuncsig is None:
            return 
        key = (funcname,) + tuple(self._currfuncsig)
        self.desc[self._funckey][key] = rtntype
        self._currfuncsig = None

    def visit_IdentifierType(self, node):
        self._pprint(node)
        t = " ".join(node.names)
        t = self._basetypes.get(t, t)
        self._currtype = t

    def visit_Decl(self, node):
        self._pprint(node)
        if isinstance(node.type, pycparser.c_ast.FuncDecl):
            self.visit(node.type)
            key = (node.name,) + self._currtype[1]
            self.desc[self._funckey][key] = self._currtype[2]
            self._currtype = None
        else:
            self.visit(node.type)

    def visit_TypeDecl(self, node):
        self._pprint(node)
        if hasattr(node.type, 'children'):
            self.visit(node.type)

    def _enumint(self, value):
        base = 10
        if value.startswith('0x') or value.startswith('-0x') or \
           value.startswith('+0x'):
            base = 16
        return int(value, base)

    def visit_Enumerator(self, node):
        self._pprint(node)
        if node.value is None:
            if len(self._currenum) == 0:
                value = 0
            else:
                value = self._currenum[-1][-1] + 1
        elif isinstance(node.value, pycparser.c_ast.Constant):
            value = self._enumint(node.value.value)
        elif isinstance(node.value, pycparser.c_ast.UnaryOp):
            if not isinstance(node.value.expr, pycparser.c_ast.Constant):
                raise ValueError("non-contant enum values not yet supported")
            value = self._enumint(node.value.op + node.value.expr.value)
        else:
            value = node.value
        self._currenum.append((node.name, value))

    def visit_Enum(self, node):
        self._pprint(node)
        self._currenum = []
        for _, child in node.children():
            self.visit(child)
        self._currtype = ('enum', node.name, tuple(self._currenum))
        self._currenum = None

    def visit_PtrDecl(self, node):
        self._pprint(node)
        self.visit(node.type)
        if self._currtype is not None and self._currtype[0] == 'function':
            self._currtype = ('function_pointer',) + self._currtype[1:]
        else:
            self._currtype = (self._currtype, '*')

    def visit_ArrayDecl(self, node):
        self._pprint(node)
        self.visit(node.type)
        self._currtype = (self._currtype, '*')

    def visit_FuncDecl(self, node):
        self._pprint(node)
        args = []
        for i, arg in enumerate(node.args.params):
            if isinstance(arg, pycparser.c_ast.EllipsisParam):
                continue
            argname = arg.name or '_{0}'.format(i)
            argtype = self.type(arg, safe=True)
            args.append((argname, argtype))
        rtntype = self.type(node.type, safe=True)
        self._currtype = ('function', tuple(args), rtntype)

    def visit_Struct(self, node):
        self._pprint(node)
        name = node.name
        if name is None:
            name = "<name-not-found>"
        self._currtype = name

    def visit_Typedef(self, node):
        self._pprint(node)
        self._currtype = None
        if not hasattr(node.type, 'children'):
            return 
        self.visit(node.type)
        name = self._currtype
        self._currtype = None
        if name is None:
            return
        if name == "<name-not-found>":
            name = node.name
        self._currtype = name


    def type(self, node, safe=False):
        self._pprint(node)
        if safe:
            stashtype = self._currtype
            self._currtype = None
        self.visit(node)
        t = self._currtype
        self._currtype = None
        if safe:
            self._currtype = stashtype
        return t

    def visit_members(self, node):
        self._pprint(node)
        for _, child in node.children():
            name = child.name
            if name.startswith('_') or name in FORBIDDEN_NAMES:
                continue
            t = self.type(child)
            if t == "<name-not-found>":
                msg = ("autodescribe: warning: anonymous struct members not "
                       "yet supported, found {0}.{1}")
                print(msg.format(self.name, name))
                continue
            elif t == ("<name-not-found>", '*'):
                msg = ("autodescribe: warning: anonymous struct pointer members "
                       "not yet supported, found {0}.{1}")
                print(msg.format(self.name, name))
                continue
            self.desc['attrs'][name] = t
        
class PycparserVarDescriber(PycparserBaseDescriber):

    _type_error_msg = "{0} is a {1}, use {2} instead."

    def __init__(self, name, root, onlyin=None, verbose=False):
        """Parameters
        -------------
        name : str
            The variable name.
        root : pycparser AST
            The root of the abstract syntax tree.
        onlyin :  str, optional
            Filename the variable described must live in.  Prevents 
            finding variables of the same name coming from other libraries.
        verbose : bool, optional
            Flag to display extra information while visiting the class.

        """
        super(PycparserVarDescriber, self).__init__(name, root, onlyin=onlyin, 
                                                                verbose=verbose)

    def visit(self, node=None):
        """Visits the variable definition node and all sub-nodes, generating 
        the description dictionary as it goes.

        Parameters
        ----------
        node : element tree node, optional
            The element tree node to start from.  If this is None, then the 
            top-level variable node is found and visited.

        """
        if node is None:
            self.load_basetypes()
            for child_name, child in self._root.children():
                if getattr(child, 'name', None) == self.name:
                    if isinstance(child, pycparser.c_ast.FuncDef):
                        raise TypeError(_type_error_msg.format(self.name, 'function', 
                                                            'PycparserFuncDescriber'))
                    if isinstance(child, pycparser.c_ast.Struct):
                        raise TypeError(_type_error_msg.format(self.name, 'struct', 
                                                            'PycparserClassDescriber'))
                    child.show()
                    self.desc['type'] = self.type(child)
                    break
        else:
            super(PycparserVarDescriber, self).visit(node)

class PycparserFuncDescriber(PycparserBaseDescriber):

    _funckey = 'signatures'

    def __init__(self, name, root, onlyin=None, verbose=False):
        """Parameters
        -------------
        name : str
            The function name.
        root : pycparser AST
            The root of the abstract syntax tree.
        onlyin :  str, optional
            Filename the class or struct described must live in.  Prevents 
            finding classes of the same name coming from other libraries.
        verbose : bool, optional
            Flag to display extra information while visiting the class.

        """
        super(PycparserFuncDescriber, self).__init__(name, root, onlyin=onlyin, 
                                                                  verbose=verbose)
        self.desc[self._funckey] = {}

    def visit(self, node=None):
        """Visits the function node and all sub-nodes, generating the description
        dictionary as it goes.

        Parameters
        ----------
        node : element tree node, optional
            The element tree node to start from.  If this is None, then the 
            top-level class node is found and visited.

        """
        if node is None:
            self.load_basetypes()
            for child_name, child in self._root.children():
                if isinstance(child, pycparser.c_ast.FuncDef) and \
                   child.decl.name == self.name:
                    self.visit(child)
                elif isinstance(child, pycparser.c_ast.Decl) and \
                     child.name == self.name:
                    self.visit(child)
        else:
            super(PycparserFuncDescriber, self).visit(node)

class PycparserClassDescriber(PycparserBaseDescriber):

    _funckey = 'methods'
    _constructvalue = 'struct'

    def __init__(self, name, root, onlyin=None, verbose=False):
        """Parameters
        -------------
        name : str
            The name, this may not have a None value.
        root : pycparser AST
            The root of the abstract syntax tree.
        onlyin :  str, optional
            Filename the class or struct described must live in.  Prevents 
            finding classes of the same name coming from other libraries.
        verbose : bool, optional
            Flag to display extra information while visiting the class.

        Notes
        -----
        It is impossible for C structs to have true member functions, only 
        function pointers.

        """
        super(PycparserClassDescriber, self).__init__(name, root, onlyin=onlyin, 
                                                                  verbose=verbose)
        self.desc['attrs'] = {}
        self.desc[self._funckey] = {}
        self.desc['parents'] = None
        self.desc['construct'] = self._constructvalue

    def visit(self, node=None):
        """Visits the struct (class) node and all sub-nodes, generating the 
        description dictionary as it goes.

        Parameters
        ----------
        node : element tree node, optional
            The element tree node to start from.  If this is None, then the 
            top-level struct (class) node is found and visited.

        """
        if node is None:
            self.load_basetypes()
            for child_name, child in self._root.children():
                if isinstance(child, pycparser.c_ast.Typedef) and \
                   isinstance(child.type, pycparser.c_ast.TypeDecl) and \
                   isinstance(child.type.type, pycparser.c_ast.Struct):
                    child = child.type.type
                if not isinstance(child, pycparser.c_ast.Struct):
                    continue
                if child.name != self.name:
                    continue
                self.visit_members(child)
        else:
            super(PycparserClassDescriber, self).visit(node)

_pycparser_describers = {
    'var': PycparserVarDescriber,
    'func': PycparserFuncDescriber,
    'class': PycparserClassDescriber, 
    }

def pycparser_describe(filename, name, kind, includes=(), defines=('XDRESS',),
                       undefines=(), verbose=False, debug=False, builddir='build'):
    """Use pycparser to describe the fucntion or struct (class).

    Parameters
    ----------
    filename : str
        The path to the file.
    name : str or None, optional
        The name, a 'None' value will attempt to infer this from the 
        filename.
    kind : str
        The kind of type to describe, valid flags are 'class', 'func', and 'var'.
    includes: list of str, optional
        The list of extra include directories to search for header files.
    defines: list of str, optional
        The list of extra macro definitions to apply.
    undefines: list of str, optional
        The list of extra macro undefinitions to apply.
    verbose : bool, optional
        Flag to diplay extra information while describing the class.
    debug : bool, optional
        Flag to enable/disable debug mode.
    builddir : str, optional
        Location of -- often temporary -- build files.

    Returns
    -------
    desc : dict
        A dictionary describing the class which may be used to generate
        API bindings.
    """
    root = astparsers.pycparser_parse(filename, includes=includes, defines=defines, 
                                      undefines=undefines, verbose=verbose, 
                                      debug=debug, builddir=builddir)
    onlyin = set([filename, filename.replace('.c', '.h')])
    describer = _pycparser_describers[kind](name, root, onlyin=onlyin, verbose=verbose)
    describer.visit()
    return describer.desc


#
#  General utilities
#

_describers = {
    'clang': clang_describe, 
    'gccxml': gccxml_describe,
    'pycparser': pycparser_describe,
    }

def describe(filename, name=None, kind='class', includes=(), defines=('XDRESS',),
             undefines=(), parsers='gccxml', verbose=False, debug=False, 
             builddir='build'):
    """Automatically describes an API element in a file.  This is the main entry point.

    Parameters
    ----------
    filename : str
        The path to the file.
    name : str or None, optional
        The name, a 'None' value will attempt to infer this from the 
        filename.
    kind : str, optional
        The kind of type to describe, valid flags are 'class', 'func', and 'var'.
    includes: list of str, optional
        The list of extra include directories to search for header files.
    defines: list of str, optional
        The list of extra macro definitions to apply.
    undefines: list of str, optional
        The list of extra macro undefinitions to apply.
    parsers : str, list, or dict, optional
        The parser / AST to use to use for the file.  Currently 'clang', 'gccxml', 
        and 'pycparser' are supported, though others may be implemented in the 
        future.  If this is a string, then this parser is used.  If this is a list, 
        this specifies the parser order to use based on availability.  If this is
        a dictionary, it specifies the order to use parser based on language, i.e.
        ``{'c' ['pycparser', 'gccxml'], 'c++': ['gccxml', 'pycparser']}``.
    verbose : bool, optional
        Flag to diplay extra information while describing the class.
    debug : bool, optional
        Flag to enable/disable debug mode.
    builddir : str, optional
        Location of -- often temporary -- build files.

    Returns
    -------
    desc : dict
        A dictionary describing the class which may be used to generate
        API bindings.
    """
    if name is None:
        name = os.path.split(filename)[-1].rsplit('.', 1)[0].capitalize()
    parser = astparsers.pick_parser(filename, parsers)
    describer = _describers[parser]
    desc = describer(filename, name, kind, includes=includes, defines=defines,
                     undefines=undefines, verbose=verbose, debug=debug, 
                     builddir=builddir)
    return desc


#
# Plugin
#

class XDressPlugin(astparsers.ParserPlugin):
    """This plugin creates automatic description dictionaries of all souce and 
    target files."""

    def __init__(self):
        super(XDressPlugin, self).__init__()
        self.pysrcenv = {}

    def defaultrc(self):
        rc = RunControl()
        rc._update(super(XDressPlugin, self).defaultrc)
        # target enviroment made up of module dicts made up of descriptions
        rc.env = {} 
        return rc

    def setup(self, rc):
        """Expands variables, functions, and classes in the rc based on 
        copying src filenames to tar filename."""
        super(XDressPlugin, self).setup(rc)
        for i, var in enumerate(rc.variables):
            if len(var) == 2:
                rc.variables[i] = (var[0], var[1], var[1])
        for i, fnc in enumerate(rc.functions):
            if len(fnc) == 2:
                rc.functions[i] = (fnc[0], fnc[1], fnc[1])
        for i, cls in enumerate(rc.classes):
            if len(cls) == 2:
                rc.classes[i] = (cls[0], cls[1], cls[1])

    def execute(self, rc):
        print("autodescribe: scraping C/C++ APIs from source")
        self.load_sidecars(rc)
        self.compute_classes(rc)
        self.compute_functions(rc)
        self.compute_variables(rc)

    def report_debug(self, rc):
        super(XDressPlugin, self).report_debug(rc)

    # Helper methods below

    def load_pysrcmod(self, srcname, rc):
        """Loads a module dictionary from a src file into the pysrcenv cache."""
        if srcname in self.pysrcenv:
            return
        pyfilename = os.path.join(rc.sourcedir, srcname + '.py')
        if os.path.isfile(pyfilename):
            glbs = globals()
            locs = {}
            exec_file(pyfilename, glbs, locs)
            if 'mod' not in locs:
                pymod = {}
            elif callable(locs['mod']):
                pymod = eval('mod()', glbs, locs)
            else:
                pymod = locs['mod']
        else:
            pymod = {}
        self.pysrcenv[srcname] = pymod

    def load_sidecars(self, rc):
        """Loads all sidecar files."""
        srcnames = set([x[1] for x in rc.variables])
        srcnames |= set([x[1] for x in rc.functions])
        srcnames |= set([x[1] for x in rc.classes])
        for x in srcnames:
            self.load_pysrcmod(x, rc)

    def compute_desc(self, name, srcname, tarname, kind, rc):
        """Returns a description dictionary for a class or function
        implemented in a source file and bound into a target file.

        Parameters
        ----------
        name : str
            Class or function name to describe.
        srcname : str
            File basename of implementation.  
        tarname : str
            File basename where the bindings will be generated.  
        kind : str
            The kind of type to describe, valid flags are 'class', 'func', and 'var'.
        rc : xdress.utils.RunControl
            Run contoler for this xdress execution.

        Returns
        -------
        desc : dict
            Description dictionary.

        """
        # description
        srcfname, hdrfname, lang, ext = find_source(srcname, sourcedir=rc.sourcedir)
        filename = os.path.join(rc.sourcedir, srcfname)
        cache = rc._cache
        if cache.isvalid(name, filename, kind):
            srcdesc = cache[name, filename, kind]
        else:
            srcdesc = describe(filename, name=name, kind=kind, includes=rc.includes, 
                               defines=rc.defines, undefines=rc.undefines, 
                               parsers=rc.parsers, verbose=rc.verbose, 
                               debug=rc.debug, builddir=rc.builddir)
            cache[name, filename, kind] = srcdesc

        # python description
        pydesc = self.pysrcenv[srcname].get(name, {})

        desc = merge_descriptions([srcdesc, pydesc])
        desc['source_filename'] = srcfname
        desc['header_filename'] = hdrfname
        desc['metadata_filename'] = '{0}.py'.format(srcname)
        if tarname is None:
            desc['pxd_filename'] = desc['pyx_filename'] = \
                                   desc['srcpxd_filename'] = None
        else:
            desc['pxd_filename'] = '{0}.pxd'.format(tarname)
            desc['pyx_filename'] = '{0}.pyx'.format(tarname)
            desc['srcpxd_filename'] = '{0}_{1}.pxd'.format(ext, tarname)
        return desc

    def adddesc2env(self, desc, env, name, srcname, tarname):
        """Adds a description to environment"""
        # Add to target environment
        # docstrings overwrite, extras accrete 
        mod = {name: desc, 'docstring': self.pysrcenv[srcname].get('docstring', ''),
               'srcpxd_filename': desc['srcpxd_filename'],
               'pxd_filename': desc['pxd_filename'],
               'pyx_filename': desc['pyx_filename']}
        if tarname not in env:
            env[tarname] = mod
            env[tarname]["name"] = tarname
            env[tarname]['extra'] = self.pysrcenv[srcname].get('extra', '')
        else:
            #env[tarname].update(mod)
            env[tarname][name] = desc
            env[tarname]['extra'] += self.pysrcenv[srcname].get('extra', '')

    def compute_classes(self, rc):
        """Computes class descriptions and loads them into the environment and 
        type system."""
        # compute all class descriptions first 
        cache = rc._cache
        env = rc.env  # target environment, not source one
        for i, (classname, srcname, tarname) in enumerate(rc.classes):
            print("autodescribe: describing " + classname)
            desc = self.compute_desc(classname, srcname, tarname, 'class', rc)
            if rc.verbose:
                pprint(desc)
            print("autodescribe: registering " + classname)
            pxd_base = desc['pxd_filename'].rsplit('.', 1)[0]         # eg, fccomp
            cpppxd_base = desc['srcpxd_filename'].rsplit('.', 1)[0]   # eg, cpp_fccomp
            class_c2py = ('{pytype}({var})',
                          ('{proxy_name} = {pytype}()\n'
                           '(<{ctype} *> {proxy_name}._inst)[0] = {var}'),
                          ('if {cache_name} is None:\n'
                           '    {proxy_name} = {pytype}()\n'
                           '    {proxy_name}._free_inst = False\n'
                           '    {proxy_name}._inst = &{var}\n'
                           '    {cache_name} = {proxy_name}\n')
                         )
            class_py2c = ('{proxy_name} = <{cytype_nopred}> {var}',
                          '(<{ctype_nopred} *> {proxy_name}._inst)[0]')
            class_cimport = (rc.package, cpppxd_base)
            kwclass = dict(
                name=classname,                                 # FCComp
                cython_c_type=cpppxd_base + '.' + classname,    # cpp_fccomp.FCComp
                cython_cimport=class_cimport,
                cython_cy_type=pxd_base + '.' + classname,      # fccomp.FCComp   
                cython_py_type=pxd_base + '.' + classname,      # fccomp.FCComp   
                cython_template_class_name=classname.replace('_', '').capitalize(),
                cython_cyimport=pxd_base,                       # fccomp
                cython_pyimport=pxd_base,                       # fccomp
                cython_c2py=class_c2py,
                cython_py2c=class_py2c,
                )
            ts.register_class(**kwclass)
            class_ptr_c2py = ('{pytype}({var})',
                              #('cdef {pytype} {proxy_name}\n'
                              # '{proxy_name} = {pytype}()\n'
                              # '(<{ctype}> {proxy_name}._inst) = {var}'),
                              ('cdef {pytype} {proxy_name} = {pytype}()\n'
                               #'{proxy_name} = {pytype}()\n'
                               '(<{ctype}> {proxy_name}._inst)[0] = {var}[0]'),
                              ('if {cache_name} is None:\n'
                               '    {proxy_name} = {pytype}()\n'
                               '    {proxy_name}._free_inst = False\n'
                               '    {proxy_name}._inst = {var}\n'
                               '    {cache_name} = {proxy_name}\n')
                             )
            class_ptr_py2c = ('{proxy_name} = <{cytype_nopred}> {var}',
                              '(<{ctype_nopred} *> {proxy_name}._inst)')
            kwclassptr = dict(
                name=(classname, '*'),
                cython_py_type=pxd_base + '.' + classname,
                cython_cy_type=pxd_base + '.' + classname,
                cython_c2py=class_ptr_c2py,
                cython_py2c=class_ptr_py2c,
                cython_cimport=kwclass['cython_cimport'],
                cython_cyimport=kwclass['cython_cyimport'],
                cython_pyimport=kwclass['cython_pyimport'],
                )
            ts.register_class(**kwclassptr)
            class_dblptr_c2py = ('{pytype}({var})',
                              ('{proxy_name} = {proxy_name}_obj._inst\n'
                               '(<{ctype} *> {proxy_name}._inst) = {var}'),
                              ('if {cache_name} is None:\n'
                               '    {proxy_name} = {pytype}()\n'
                               '    {proxy_name}._free_inst = False\n'
                               '    {proxy_name}._inst = {var}\n'
                               '    {proxy_name}_list = [{proxy_name}]\n'
                               '    {cache_name} = {proxy_name}_list\n')
                             )
            class_dblptr_py2c = ('{proxy_name} = <{cytype_nopred}> {var}[0]',
                                 '(<{ctype_nopred} **> {proxy_name}._inst)')
            kwclassdblptr = dict(
                name=((classname, '*'), '*'),
                cython_c2py=class_dblptr_c2py,
                cython_py2c=class_dblptr_py2c,
                cython_cimport=kwclass['cython_cimport'],
                cython_cyimport=kwclass['cython_cyimport'],
                cython_pyimport=kwclass['cython_pyimport'],
                )
            ts.register_class(**kwclassdblptr)
            cache.dump()
            self.adddesc2env(desc, env, classname, srcname, tarname)
            if 0 == i%rc.clear_parser_cache_period:
                astparsers.clearmemo()

    def compute_functions(self, rc):
        """Computes function descriptions and loads them into the environment."""
        env = rc.env
        cache = rc._cache
        for i, (funcname, srcname, tarname) in enumerate(rc.functions):
            print("autodescribe: describing " + funcname)
            desc = self.compute_desc(funcname, srcname, tarname, 'func', rc)
            if rc.verbose:
                pprint(desc)
            cache.dump()
            self.adddesc2env(desc, env, funcname, srcname, tarname)
            if 0 == i%rc.clear_parser_cache_period:
                astparsers.clearmemo()

    def compute_variables(self, rc):
        """Computes variables descriptions and loads them into the environment."""
        env = rc.env
        cache = rc._cache
        for i, (varname, srcname, tarname) in enumerate(rc.variables):
            print("autodescribe: describing " + varname)
            desc = self.compute_desc(varname, srcname, tarname, 'var', rc)
            if rc.verbose:
                pprint(desc)
            cache.dump()
            self.adddesc2env(desc, env, varname, srcname, tarname)
            if 0 == i%rc.clear_parser_cache_period:
                astparsers.clearmemo()

