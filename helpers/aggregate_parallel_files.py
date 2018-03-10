#!/usr/bin/env python

import glob
import multiprocessing as mp

import numpy as np
import xarray as xr

# This should be an input, this is the search string that is assumed to match
# the output files to be aggregated.
file_search = "icar_restart_output_{ens}_*"

# number of processors to parallelize reading the files over
n_processors = 10

def load_file(file_name):
    '''Load a netcdf dataset into memory'''
    return xr.open_dataset(file_name).load()


def get_dims(dataset, section="d"):
    '''Get the global attributes defining the domain, memory, or tile space'''
    results = []
    for axis in ["i","j","k"]:
        for position in ["s","e"]:
            results.append(int(dataset.attrs[axis + section + position]))
    return results

def get_dim_offset(dims):
    '''Return x_offset, y_offset
    For the staggered dims, offset=1, otherwise offset=0'''
    x_off = 0
    if 'lon_u' in dims: x_off = 1

    y_off = 0
    if 'lat_v' in dims: y_off = 1

    return x_off, y_off

def set_up_dataset(d):
    '''Create a dataset to cover the entire domain with the variables present in d

    d : an input dataset covering part of the domain
    d must have global attributes ids, ide, jds, jde, kds, kde that define the full domain

    A new dataset is created with all the variables+attributes in d covering the full domain
    '''
    ids, ide, jds, jde, kds, kde = get_dims(d, section='d')
    nx = ide - ids + 1
    ny = jde - jds + 1
    nz = kde - kds + 1

    data_vars = dict()

    for v in d.variables:
        coords = d[v].coords
        dims   = d[v].dims
        name   = d[v].name
        attrs  = d[v].attrs

        x_off, y_off = get_dim_offset(dims)

        if len(dims) == 2:
            data = np.zeros((ny + y_off, nx + x_off))
        if len(dims) == 3:
            data = np.zeros((d.dims[dims[0]], ny + y_off, nx + x_off))
        if len(dims) == 4:
            nt = d.dims[dims[0]]
            nz = d.dims[dims[1]]
            data = np.zeros((nt, nz, ny + y_off, nx + x_off))

        # print(data.shape, dims, name, attrs)
        data_vars[v] = xr.DataArray(data, dims=dims, name=name, attrs=attrs)

    return xr.Dataset(data_vars, attrs=d.attrs)



def agg_file(first_file):
    '''Aggregated all files that come from the same time step as first_file

    first_file should have _001_ in the filename somewhere.  This will be replaced
    with * to search for all matching files from this date. Once files are found, a
    dataset containing the entire domain is created and the data from each file are
    added to the master dataset.

    Result: aggregated dataset is written to a netcdf file'''

    print(first_file)
    date_search = first_file.replace("_001_","*")
    this_date_files = glob.glob(date_search)
    this_date_files.sort()

    # Run this in serial instead of using the parallel map functionality.
    # all_data = []
    # for f in this_date_files:
    #     all_data.append(load_file(f))

    results = pool.map_async(load_file, this_date_files)
    all_data = results.get()


    data_set = set_up_dataset(all_data[0])

    ids, ide, jds, jde, kds, kde = get_dims(all_data[0], section='d')
    for d in all_data:
        ims, ime, jms, jme, kms, kme = get_dims(d, section='m')
        its, ite, jts, jte, kts, kte = get_dims(d, section='t')

        xts, xte = its - ims, ite - ims + 1
        yts, yte = jts - jms, jte - jms + 1
        zts, zte = kts - kms, kte - kms + 1

        xs, xe = its - ids, ite - ids + 1
        ys, ye = jts - jds, jte - jds + 1
        zs, ze = kts - kds, kte - kds + 1


        for v in d.variables:
            dims   = d[v].dims
            x_off, y_off = get_dim_offset(dims)

            if len(dims) == 2:
                data_set[v].values[ys:ye, xs:xe] = d[v].values[yts:yte, xts:xte]
            if len(dims) == 3:
                if dims[0] == "time":
                    data_set[v].values[:, ys:ye+y_off, xs:xe+x_off] = d[v].values[:, yts:yte+y_off, xts:xte+x_off]
                else:
                    data_set[v].values[zs:ze, ys:ye+y_off, xs:xe+x_off] = d[v].values[zts:zte, yts:yte+y_off, xts:xte+x_off]
            if len(dims) == 4:
                data_set[v].values[:,zs:ze, ys:ye+y_off, xs:xe+x_off] = d[v].values[:,zts:zte, yts:yte+y_off, xts:xte+x_off]

    data_set.to_netcdf(first_file.replace("_001_","_"))

def main():
    first_files = glob.glob(file_search.format(ens="001"))
    first_files.sort()

    # For some reason running the parallelization this far out seems to have far worse performance...
    #  would map_async be faster for some reason?  I assume map is still parallel.
    # pool.map(agg_file, first_files)

    for f in first_files:
        agg_file(f)


pool = mp.Pool(n_processors)

if __name__ == '__main__':
    main()
