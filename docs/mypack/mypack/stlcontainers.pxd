###################
###  WARNING!!! ###
###################
# This file has been autogenerated

# Cython imports
from libcpp.set cimport set as cpp_set
from libcpp.vector cimport vector as cpp_vector
from cython.operator cimport dereference as deref
from cython.operator cimport preincrement as inc
from libcpp.string cimport string as std_string
from libcpp.utility cimport pair
from libcpp.map cimport map as cpp_map
from libcpp.vector cimport vector as cpp_vector
from libc cimport stdio
from cpython.version cimport PY_MAJOR_VERSION
from cpython.ref cimport PyTypeObject, Py_INCREF, Py_XDECREF
from cpython.type cimport PyType_Ready
from cpython.object cimport PyObject
from cpython.object cimport Py_LT, Py_LE, Py_EQ, Py_NE, Py_GT, Py_GE

# Python Imports
cimport numpy as np

# Local imports
cimport mypack_extra_types

cimport numpy as np


# Cython Imports For Types
cimport mypack_extra_types
from libcpp.string cimport string as std_string

cdef extern from "Python.h":
    ctypedef Py_ssize_t Py_ssize_t

    cdef long Py_TPFLAGS_DEFAULT 
    cdef long Py_TPFLAGS_BASETYPE 
    cdef long Py_TPFLAGS_CHECKTYPES
    cdef long Py_TPFLAGS_HEAPTYPE

    ctypedef struct PyGetSetDef:
        char * name

    ctypedef struct PyTypeObject:
        char * tp_name
        int tp_basicsize
        int tp_itemsize
        object tp_alloc(PyTypeObject *, Py_ssize_t)
        void tp_dealloc(object)
        object tp_richcompare(object, object, int)
        object tp_new(PyTypeObject *, object, object)
        object tp_str(object)
        object tp_repr(object)
        long tp_hash(object)
        long tp_flags
        char * tp_doc
        PyMemberDef * tp_members
        PyGetSetDef * tp_getset
        PyTypeObject * tp_base
        void tp_free(void *)
        # This is a dirty hack by declaring to Cython both the Python 2 & 3 APIs
        int (*tp_compare)(object, object)      # Python 2
        void * (*tp_reserved)(object, object)  # Python 3

# structmember.h isn't included in Python.h for some reason
cdef extern from "structmember.h":
    ctypedef struct PyMemberDef:
        char * name
        int type
        Py_ssize_t offset
        int flags
        char * doc

cdef extern from "numpy/arrayobject.h":

    ctypedef object (*PyArray_GetItemFunc)(void *, void *)
    ctypedef int (*PyArray_SetItemFunc)(object, void *, void *)
    ctypedef void (*PyArray_CopySwapNFunc)(void *, np.npy_intp, void *, np.npy_intp, np.npy_intp, int, void *)
    ctypedef void (*PyArray_CopySwapFunc)(void *, void *, int, void *)
    ctypedef int (*PyArray_CompareFunc)(const void* d1, const void *, void *)
    ctypedef int (*PyArray_ArgFunc)(void *, np.npy_intp, np.npy_intp *, void *)
    ctypedef void (*PyArray_DotFunc)(void *, np.npy_intp, void *, np.npy_intp, void *, np.npy_intp, void *)
    ctypedef int (*PyArray_ScanFunc)(stdio.FILE *, void *, void *, void *)
    ctypedef int (*PyArray_FromStrFunc)(char *, void *, char **, void *)
    ctypedef np.npy_bool (*PyArray_NonzeroFunc)(void *, void *)
    ctypedef void (*PyArray_FillFunc)(void *, np.npy_intp, void *)
    ctypedef void (*PyArray_FillWithScalarFunc)(void *, np.npy_intp, void *, void *)
    ctypedef int (*PyArray_SortFunc)(void *, np.npy_intp, void *)
    ctypedef int (*PyArray_ArgSortFunc)(void *, np.npy_intp *, np.npy_intp, void *)
    ctypedef np.NPY_SCALARKIND (*PyArray_ScalarKindFunc)(np.PyArrayObject *)

    ctypedef struct PyArray_ArrFuncs:
        np.PyArray_VectorUnaryFunc ** cast
        PyArray_GetItemFunc *getitem
        PyArray_SetItemFunc *setitem
        PyArray_CopySwapNFunc *copyswapn
        PyArray_CopySwapFunc *copyswap
        PyArray_CompareFunc *compare
        PyArray_ArgFunc *argmax
        PyArray_DotFunc *dotfunc
        PyArray_ScanFunc *scanfunc
        PyArray_FromStrFunc *fromstr
        PyArray_NonzeroFunc *nonzero
        PyArray_FillFunc *fill
        PyArray_FillWithScalarFunc *fillwithscalar
        PyArray_SortFunc *sort
        PyArray_ArgSortFunc *argsort
        PyObject *castdict
        PyArray_ScalarKindFunc *scalarkind
        int **cancastscalarkindto
        int *cancastto
        int listpickle

    cdef void PyArray_InitArrFuncs(PyArray_ArrFuncs *)

    ctypedef struct PyArray_ArrayDescr:
        PyArray_Descr * base
        PyObject  *shape

    cdef void ** PyArray_API

    cdef PyTypeObject * PyArrayDescr_Type
    
    ctypedef struct PyArray_Descr:
        Py_ssize_t ob_refcnt
        PyTypeObject * ob_type
        PyTypeObject * typeobj
        char kind
        char type
        char byteorder
        int flags
        int type_num
        int elsize
        int alignment
        PyArray_ArrayDescr * subarray
        PyObject * fields
        PyObject * names
        PyArray_ArrFuncs * f

    cdef int PyArray_RegisterDataType(PyArray_Descr *)

    cdef object PyArray_Scalar(void *, PyArray_Descr *, object)

cdef extern from "mypack_extra_types.h" namespace "mypack_extra_types":
    cdef cppclass MemoryKnight[T]:
        MemoryKnight() nogil except +
        T * defnew() nogil except +
        T * renew(void *) nogil except +
        void deall(T *) nogil except +

# std_string dtype
ctypedef struct PyXDStr_Type:
    Py_ssize_t ob_refcnt
    PyTypeObject *ob_typ
    std_string obval

cdef object pyxd_str_getitem(void * data, void * arr)
cdef int pyxd_str_setitem(object value, void * data, void * arr)
cdef void pyxd_str_copyswapn(void * dest, np.npy_intp dstride, void * src, np.npy_intp sstride, np.npy_intp n, int swap, void * arr)
cdef void pyxd_str_copyswap(void * dest, void * src, int swap, void * arr)
cdef np.npy_bool pyxd_str_nonzero(void * data, void * arr)


# SetUInt
cdef class _SetIterUInt(object):
    cdef cpp_set[mypack_extra_types.uint32].iterator * iter_now
    cdef cpp_set[mypack_extra_types.uint32].iterator * iter_end
    cdef void init(_SetIterUInt, cpp_set[mypack_extra_types.uint32] *)

cdef class _SetUInt:
    cdef cpp_set[mypack_extra_types.uint32] * set_ptr
    cdef public bint _free_set




# MapIntDouble
cdef class _MapIterIntDouble(object):
    cdef cpp_map[int, double].iterator * iter_now
    cdef cpp_map[int, double].iterator * iter_end
    cdef void init(_MapIterIntDouble, cpp_map[int, double] *)

cdef class _MapIntDouble:
    cdef cpp_map[int, double] * map_ptr
    cdef public bint _free_map




