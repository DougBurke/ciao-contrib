#
#  Copyright (C) 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020
#    Smithsonian Astrophysical Observatory
#
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License along
#  with this program; if not, write to the Free Software Foundation, Inc.,
#  51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""
Routines used when merging and combining data.
"""

import os
import tempfile

import numpy as np

import cxcdm
import paramio
import pycrates
import stk

from ciao_contrib.stacklib import make_stackfile
from ciao_contrib.region.fov import AxisRange

import ciao_contrib.cxcdm_wrapper as cw
import ciao_contrib.logger_wrapper as lw
import ciao_contrib.runtool as rt

import coords.format
import coords.utils

import ciao_contrib._tools.fileio as fileio
import ciao_contrib._tools.fluximage as fi
from ciao_contrib._tools.obsinfo import ObsInfo
import ciao_contrib._tools.run as run
import ciao_contrib._tools.utils as utils

from ciao_contrib._tools.headers import HeaderMerge

__all__ = (
    "match_obsid",
    "match_obsid_asol",
    "postprocess_asol",
    "reproject_event_files",
    "merge_event_files")

lgr = lw.initialize_module_logger('_tools.merging')
v1 = lgr.verbose1
v2 = lgr.verbose2
v3 = lgr.verbose3
v4 = lgr.verbose4


def match_obsid(obsinfos, infiles, label):
    """Return the infiles array so that each infile
    has the same obsid/obi as the corresponding entry in the
    obsinfos array.

    Excess entries (those in infiles that do not match any obsid/obi in
    obsinfos) will be ignored, with a warning message displayed.

    If any obsid has no matching file then an error is raised. It is
    an error for there to be multiple matches for an obsid.

    obsinfos is an array of ciao_contrib._tools.utils.ObsInfo objects
    and is assumed to have no repeated elements.

    The label argument is used in error messages and should be
    something like "mask".

    TODO: how should "CALDB" and "NONE" be handled if found
    in infiles?
    """

    v3("Matching observations and files for label={}".format(label))

    # The OBI is only used in the comparison when the obsid is a known
    # multi-OBI dataset.
    #
    def make_key(obsid, cycle=None):
        if cycle is None:
            cycle = obsid.cycle
        if utils.is_multi_obi_obsid(obsid.obsid):
            return (obsid.obsid, cycle, obsid.obi)
        else:
            return (obsid.obsid, cycle)

    cache = {}
    for infile in infiles:
        # Assume this obsid object is unique; for now skip if multiple are
        # found, warning the user. Really we should error out, since we do
        # not know which is the better file, but for now just use the first
        # value.
        obsid = fileio.get_obsid_object(infile)
        v4("File {} has obsid {}".format(infile, obsid))

        key = make_key(obsid)
        if key in cache:
            # I could use obsid as the argument, rather than obsid.obsid,
            # but in some tests (with multi-obi data) it was reporting
            # <obsid>e1 rather than <obsid> or <obsid>_<obi>, so I have
            # switched to obsid.obsid instead (when I should really try
            # and find out why).
            v1("Skipping {} file {} as it has the same ObsId ({}) as {}".format(
                label, infile, obsid.obsid, cache[key]))
            continue

        cache[key] = infile

    v3("{} files have obsinfos: {}".format(label, cache))

    # We need to know whether to worry about interleaved-mode observations.
    # The elements of obsinfos only have a non-None .obsid.cycle field when
    # we care about interleaved mode.
    #
    out = []
    for obsinfo in obsinfos:
        obsid = obsinfo.obsid
        key = make_key(obsid)
        v4("Looking for match for obsid {}: key={}".format(obsid, key))

        try:
            match = cache[key]
            del cache[key]

        except KeyError:
            emsg = "There is no {} file for ObsId {}.".format(label, obsid)
            if obsid.cycle is None:
                key = make_key(obsid, cycle='P')
                try:
                    match = cache[key]
                    del cache[key]
                    v4("Looking for {} - assume ObsId {} is primary".format(label, obsid))

                except KeyError:
                    raise ValueError(emsg)

            else:
                raise ValueError(emsg)

        v3("Matched {} for {} to {}".format(label, key, match))
        out.append(match)

    # Let the user know if we have any unmatched files.
    #
    for (key, filename) in cache.items():
        obsid = key[0]
        obscycle = key[1]
        msg = "Skipping {} file {} (ObsId {}".format(label, filename, obsid)

        if obscycle not in [None, 'None']:
            msg += " Cycle {}".format(obscycle)

        if len(key) == 3:
            msg += " OBI {}".format(key[2])

        msg += ")"
        v1(msg)

    return out


def match_obsid_asol(obsinfos, asolfiles):
    """Return the asolfiles array so that each entry corresponds
    to an array of aspect solutions for the obsid in the matching
    position (in general there will only be one but there may be
    several; if so they are in time order).

    obsinfos is an array of ciao_contrib._tools.utils.ObsId objects.
    We assume that interleaved-mode observations use the same name
    for the aspect solution for the e1 and e2 versions of the file.
    OBI support is included (i.e. the OBI_NUM value must match between
    the obsinfo and asol file(s) as well as the OBS_ID).

    An error is raised if there is no matching asolfile for any entry
    in obsinfos.

    Excess asol files are ignored (a warning is displayed).

    We perform a very-simple check to see if each element of
    asolfiles is an asol file.
    """

    # The OBI is only used in the comparison when the obsid is a known
    # multi-OBI dataset.
    #
    def make_key(obsid):
        if utils.is_multi_obi_obsid(obsid.obsid):
            return (obsid.obsid, obsid.obi)
        else:
            return obsid.obsid

    aobsids = {}
    for asolfile in asolfiles:
        fileio.validate_asol(asolfile)
        # do not use the .cycle field as it should be None
        obsid = fileio.get_obsid_object(asolfile)
        key = make_key(obsid)
        try:
            aobsids[key].add(asolfile)
        except KeyError:
            aobsids[key] = set([asolfile])

    out = []
    keys = []
    for obsinfo in obsinfos:
        obsid = obsinfo.obsid
        key = make_key(obsid)
        keys.append(key)
        try:
            fnames = aobsids[key]
        except KeyError:
            raise ValueError("There is no aspect solution for ObsId {}.".format(obsid))
        except AttributeError:
            raise IOError("*Internal error* match_obsid_asol sent {}/{} rather than ObsInfo.".format(obsinfo, type(obsinfo)))

        out.append(fileio.sort_mjd(fnames))

    # Let the user know what files we could not match
    for (key, infiles) in aobsids.items():
        if key in keys:
            continue
        for infile in infiles:
            v1("Skipping asol file {} (ObsId {})".format(infile, key[0]))

    return out


# start file names

def name_coadd_img(outdir, outhead, enband):
    """The name of the coadded image."""

    return "{}{}{}.img".format(outdir, outhead, enband)


def name_coadd_thresh_img(outdir, outhead, enband):
    """The name of the coadded thresholded image."""

    return "{}{}{}_thresh.img".format(outdir, outhead, enband)


def name_coadd_flux(outdir, outhead, enband):
    """The name of the coadded fluxed image."""

    return "{}{}{}_flux.img".format(outdir, outhead, enband)


def name_coadd_expmap(outdir, outhead, enband):
    """The name of the coadded exposure map."""

    return "{}{}{}.expmap".format(outdir, outhead, enband)


def name_coadd_thresh_expmap(outdir, outhead, enband):
    """The name of the coadded thresholded exposure map."""

    return "{}{}{}_thresh.expmap".format(outdir, outhead, enband)


def name_coadd_psfmap(outdir, outhead, enband, thresh=False):
    """The name of the coadded PSF map."""

    head = "{}{}{}".format(outdir, outhead, enband)
    mid = "_thresh" if thresh else ""
    return "{}{}.psfmap".format(head, mid)


def obsid_asol_name(outdir, outhead, obsid):
    """Returns the name of the combined aspect solution for
    the given obsid.
    """

    return "{}{}{}_asol.merged.fits".format(outdir, outhead, obsid)


def obsid_reproj_evt_name(outdir, outhead, obsid):
    """Return the name of the reprojected event file for the obsid."""

    return "{}{}{}_reproj_evt.fits".format(outdir, outhead, obsid)


def merged_evt_name(outdir, outhead):
    """Return the name of the merged event file given
    the outdir and outhead arguments."""

    return "{}{}merged_evt.fits".format(outdir, outhead)


# TODO:
#    remove this routine as it is better to explicitly deal with
#    an array of aspect solutions rather than flip between
#    stacks and arrays when necessary.
#
def postprocess_asol(asolfiles):
    """Given the output of match_obsid_asol return an array
    where each element is the aspect solution for the obsid,
    when there's only one, or a comma-separated list,
    when there are multiple asol files.
    """

    # This routine used to merge the asol files, then convert to a
    # stack file, when given multiple asol files for an obsid.
    # Going back to a comma-separated list.
    #
    out = []
    for asolfile in asolfiles:
        if len(asolfile) == 0:
            raise ValueError("Sent an empty array of aspect solutions.")
        # elif len(asolfile) == 1:
        #     out.append(asolfile[0])
        else:
            out.append(','.join(asolfile))

    return out


def modify_event_file_keywords(origdir, evtfile,
                               asolfile=None,
                               bpixfile=None,
                               maskfile=None,
                               dtffile=None,
                               mtlfile=None,
                               fltfile=None
                               ):
    """Change the *FILE keywords to point to the
    original location of the eventfile (in origdir).

    This is for the case when you have changed the location of the event
    file - e.g. with reproject_event_files and the output is in a
    different directory - and you want to update the keywords to point
    to the ancillary files. So origdir should be the relative path
    from the location of evtfile - e.g. if evtfile=merged/6163_evt.fits
    and the original location was 6163/repro/ then origdir should be
    ../6163/repro/

    Any of the file arguments that are not None is used as the keyword value,
    otherwise the current value has origdir appended to it and - if it
    exists - then it is used.

    There is currently no check to see whether the 'corrected' keyword
    actually exists (which allows you to input a comma-separated
    array of values for the asolfile argument).

    The input file (evtfile) must be a table.

    The support for PBKFILES was removed in CIAO 4.6.
    """

    epath = os.path.dirname(evtfile)

    checkdir = os.path.join(epath, origdir)
    if not os.path.isdir(checkdir):
        raise IOError("No directory {} found relative to {}".format(origdir, evtfile))

    # Use cxcdm module to manipulate the keywords
    #
    bl = cxcdm.dmTableOpen(evtfile, update=True)
    store = {'ASOLFILE': asolfile,
             'BPIXFILE': bpixfile,
             'DTFFILE': dtffile,
             'FLTFILE': fltfile,
             'MASKFILE': maskfile,
             'MTLFILE': mtlfile}

    try:
        for dd in cxcdm.dmBlockGetKeyList(bl):
            key = cxcdm.dmGetName(dd)
            try:
                newval = store[key]
            except KeyError:
                continue

            oldval = cxcdm.dmGetData(dd)
            if newval is None:
                if key == 'ASOLFILE':
                    newvals = [os.path.join(origdir, oval) for
                               oval in stk.build(oldval)]
                    newval = ",".join(newvals)
                else:
                    newval = os.path.join(origdir, oldval)

            cxcdm.dmSetData(dd, newval)

            del store[key]
            if len(store) == 0:
                break

    finally:
        cxcdm.dmTableClose(bl)


def update_ancillary_keywords(infile, outfile, asolfile):
    "Update the ancillary keywords in the reprojected event file if necessary."

    origdir = os.path.dirname(infile)
    outdir = os.path.dirname(outfile)
    if origdir == outdir:
        return

    origdir = os.path.abspath(origdir)
    outdir = os.path.abspath(outdir)
    relpath = os.path.relpath(origdir, start=outdir)

    if asolfile.startswith('@'):
        asolstk = stk.build(asolfile)
    else:
        asolstk = [asolfile]

    relasol = []
    for afile in asolstk:
        adir = os.path.abspath(afile)
        arel = os.path.relpath(adir, start=outdir)
        relasol.append(arel)

    modify_event_file_keywords(relpath,
                               outfile,
                               asolfile=",".join(relasol))


# def reproject_events_task_old(infile, ra0, dec0, asolfile, outfile,
#                              tmpdir="/tmp/",
#                              verbose=0,
#                              clobber=False):
#    """Reproject (or copy) the event file.
#
#    This is left in as a reference copy whilst we check that the
#    new technique (reprojecting without the aspect solution) is
#    okay.
#    """
#
#    if clobber:
#        clstr = "yes"
#    else:
#        clstr = "no"
#
#    # reproject_events may produce invalid output if the RA
#    # of the reference location is < 0.
#    if ra0 < 0.0:
#        ra0 += 360.0
#
#    with rt.new_pfiles_environment(ardlib=False):
#
#        (ra, dec) = fileio.get_tangent_point(infile)
#        if ra == ra0 and dec == dec0:
#            v3("No need to reproject {}, so copying.".format(infile))
#            run.dmcopy(infile, outfile, clobber=clobber)
#
#        else:
#            # what is the TIME range of the aspect file(s)
#            atimes = []
#            for afile in stk.build(asolfile):
#                v3("Finding time range of aspect file: {}".format(afile))
#                (t1, t2) = fileio.get_minmax_times(afile)
#                atimes.append("{}:{}".format(t1, t2))
#                v3(" >> {}".format(atimes[-1]))
#
#            if len(atimes) == 0:
#                v1("Unexpected: no time ranges found from aspect solution for {}".format(infile))
#                timefilter = ""
#            else:
#                timefilter = "[time={}]".format(",".join(atimes))
#
#            # It looks like the [subspace -sky] filter has to be done on a
#            # separate dmcopy call, which is annoying
#            v3("Copying evt file to clear out subspace and filter times")
#            tmpfile1 = tempfile.NamedTemporaryFile(dir=tmpdir, suffix=".evt")
#            tmpfile2 = tempfile.NamedTemporaryFile(dir=tmpdir, suffix=".evt")
#            run.dmcopy("{}{}".format(infile, timefilter),
#                       tmpfile1.name, clobber=True)
#            run.dmcopy("{}[subspace -sky]".format(tmpfile1.name),
#                       tmpfile2.name, clobber=True)
#            tmpfile1.close()
#
#            v3("About to reproject events file.")
#            run.punlearn('reproject_events')
#            run.run('reproject_events',
#                    ['infile=' + tmpfile2.name,
#                     #   "infile={}{}[subspace -sky]".format(infile, timefilter),
#                     'outfile=' + outfile,
#                     "match={} {}".format(ra0, dec0),
#                     'aspect=' + asolfile,
#                     'clobber=' + clstr,
#                     "verbose={}".format(verbose)
#                     ])
#
#            run.update_column_range(outfile, verbose=verbose)
#
#            # Since this adds relative paths we have decided not to
#            # do this.
#            # update_ancillary_keywords(infile, outfile, asolfile)

def reproject_events_task(infile, ra0, dec0, outfile,
                          tmpdir="/tmp/",
                          verbose=0,
                          clobber=False,
                          tol=1.4e-5):
    """Reproject (or copy) the event file. The copy
    happens if the tangent points are separated by no more
    than tol degrees. The default tolerance (1.4e-5 degrees)
    corresponds to 0.05 arcsec.

    The copy is done by dmcopy rather than cp so that the
    history of the copy is recorded.
    """

    clstr = "yes" if clobber else "no"

    # reproject_events may produce invalid output if the RA
    # of the reference location is < 0.
    if ra0 < 0.0:
        ra0 += 360.0

    with rt.new_pfiles_environment(ardlib=False):

        (ra, dec) = fileio.get_tangent_point(infile)
        sepdeg = coords.utils.point_separation(ra0, dec0, ra, dec)
        sepasec = sepdeg * 3600.0
        v2("Separation={} arcsec between reference and {}".format(sepasec,
                                                                  infile))
        if sepdeg < tol:
            v3("No need to reproject {}, so copying.".format(infile))
            run.dmcopy(infile, outfile, option="all", clobber=clobber)

        else:
            # If there are any spatial filters on the input event files - e.g.
            # if the original input was populated via a call like
            #    @evt.lis[x=1000:7000]
            # then we need to make sure that the [subspace -sky] filter is
            # applied to an event file created from the spatially filtered
            # data, since stacking the DM filters - e.g.
            #    [x=1000:7000][subspace -sky]
            # does not work (ie the sky subspace is not lost as we want it).
            #
            if "[" in infile:
                v3("Copying evt file to apply any subspace filters: " +
                   "{}".format(infile))
                tmpfile = tempfile.NamedTemporaryFile(dir=tmpdir,
                                                      suffix=".evt")
                run.dmcopy(infile, tmpfile.name, option="all", clobber=True)
                evtname = tmpfile.name

            else:
                evtname = infile

            v3("About to reproject events file ({})".format(evtname))
            run.punlearn('reproject_events')
            run.run('reproject_events',
                    ["infile={}[subspace -sky]".format(evtname),
                     'outfile=' + outfile,
                     "match={} {}".format(ra0, dec0),
                     'aspect=',
                     'clobber=' + clstr,
                     "verbose={}".format(verbose)
                     ])

            run.update_column_range(outfile, verbose=verbose)


def reproject_event_files(taskrunner,
                          labelconv,
                          preconditions,
                          infiles,
                          outfiles,
                          ra,
                          dec,
                          clobber=False,
                          verbose=0,
                          tmpdir="/tmp",
                          tol=1.4e-5,
                          parallel=False):
    """Given a list of event files (infiles), reproject them to the given
    match value (ra and dec which are in decimal degrees).
    Those files whose tangent point match ra and dec are
    copied rather than reprojected.

    If parallel is True then the reprojection is done in parallel.

    The reprojection is done by calling reproject_events with
    aspect blank and match set to "<ra> <dec>". This means that
    the EDSER positions are maintained (for ACIS data), but it
    does require that the input events have been previously
    passed through reproject_events or foo_process_events IF
    the aspect solution has been modified (e.g. via reproject_aspect).

    A 'subspace -sky' filter is added to ensure that any spatial
    filters applied to the file will not be passed onto the reprojected
    version, since there is no guarantee that they will be valid.

    The tol parameter governs whether two event files are considered
    close enough to mean that reprojection is not needed; instead
    dmcopy will be used to copy the original file over. The tol
    parameter is in degrees and the default value (1.4e-5) corresponds
    to 0.05 arcsec. Note that the comparison is done on the tangent
    point of the event file, as given by the NOM keywords.
    """

    nevt = len(infiles)
    v3("Reprojecting {} event files to ra={} dec={}".format(nevt, ra, dec))

    stask = labelconv("reproj-obsids-start")
    if nevt == 1:
        lbl = ""
    else:
        lbl = "s"
    taskrunner.add_barrier(stask, preconditions,
                           "Reprojecting {} event file{} to a common tangent point.".format(nevt, lbl))

    tasks = []
    for (infile, outfile) in zip(infiles, outfiles):
        task = labelconv(outfile)
        taskrunner.add_task(task, [stask],
                            reproject_events_task,
                            infile, ra, dec, outfile,
                            tol=tol,
                            tmpdir=tmpdir, verbose=verbose,
                            clobber=clobber)
        tasks.append(task)

    etask = labelconv("reproj-obsids-end")
    taskrunner.add_barrier(etask, tasks)
    return etask


def parse_lookup_table(filename):
    """Parse a lookup table
    """

    out = []
    with open(filename, 'r') as fh:
        for l in fh.readlines():
            if l.strip() == '':
                continue

            toks = l.split()
            if len(toks) != 2:
                raise ValueError("Unexpected merging rule: {}".format(l))

            out.append(toks)

    return out


def adjust_rule(key, rule, obsinfos):
    """Adjust the rule given the hdr values.

    The key and keys in the dictionaries in the
    observations are assumed to use the same case.

    If there is only one file (length of obsinfos is 1)
    then the rule is not adjusted.
    """

    if len(obsinfos) == 1:
        return (key, rule)

    if rule.startswith('Merge-'):
        return adjust_merge_rule(key, rule, obsinfos)
    elif rule.startswith('WarnOmit-'):
        return adjust_warnomit_rule(key, rule, obsinfos)
    else:
        return (key, rule)


def adjust_warnomit_rule(key, rule, obsinfos):
    """Convert to SKIP if any of the values are
    missing or vary by more than the specified amount
    of the first value.
    """

    v4("Rule=WarnOmit key={} rule={}".format(key, rule))
    try:
        tol = float(rule[9:])
    except ValueError:
        raise ValueError("Invalid WarnOmit rule: {}".format(rule))

    try:
        fval = float(obsinfos[0].get_keyword(key))
    except (KeyError, ValueError):
        return (key, "SKIP")

    for obs in obsinfos[1:]:
        try:
            val = float(obs.get_keyword(key))
        except (KeyError, ValueError):
            return (key, "SKIP")

        if abs(val - fval) > tol:
            return (key, "SKIP")

    # Could remove this rule, but want to catch any errors I may
    # have made by leaving this in
    return (key, rule)


def adjust_merge_rule(key, rule, obsinfos):
    "Convert to PUT_STRING if any of the values do not match."

    v4("Rule=Merge key={} rule={}".format(key, rule))
    toks = rule.split(";")
    if len(toks) != 2:
        raise ValueError("Invalid Merge/Force rule: {}".format(rule))

    outval = toks[0][6:]
    defval = toks[1][6:]

    try:
        fval = obsinfos[0].get_keyword(key)
    except KeyError:
        fval = defval

    for obs in obsinfos[1:]:
        try:
            val = obs.get_keyword(key)
        except KeyError:
            val = defval

        if val != fval:
            return (key, "PUT_STRING-{}".format(outval))

    # Could remove this rule, but want to catch any errors I may
    # have made by leaving this in
    return (key, rule)


# Note:
#   the merging rules depend on whether the obsinfo values
#   are for the "original" or "reprojected" event files (only
#   really an issue for merge_obs, not so much flux_obs which
#   only uses the reprojected versions). Prior to the use of
#   obsinfo objects, merge_obs sent in the headers of the
#   original event files, whereas now we use the reprojected
#   files (the reason for this change was to ensure that the
#   correct aspect solutions were being used elsewhere in the
#   code). DJB thinks the current behavior, although a change,
#   is acceptable (i.e. a case can be made for it), so let's
#   see how the community reacts (or even notices).
#
def create_lookup_table(origtable, obsinfos,
                        tmpdir="/tmp/"):
    """Create a lookup table based on the rules in
    origtable (a file name) and the headers for the
    data.

    Rule changes (if values are different):

      key Merge-<a>;Force-<b> -> key PUT_STRING-<a>
      key WarnOmit-<a>        -> key SKIP

    The return value is a NamedTemporaryFile object
    which contains the new rules to use.
    """

    v4("create_lookup_table: origtable={}".format(origtable))
    orig = parse_lookup_table(origtable)
    out = []
    for (key, rule) in orig:
        out.append(adjust_rule(key, rule, obsinfos))

    fh = tempfile.NamedTemporaryFile(dir=tmpdir, mode='w+',
                                     suffix=".ltab")
    v4("** adjusted lookup table ({})".format(fh.name))
    for (key, rule) in out:
        omsg = "{} {}".format(key, rule)
        fh.write(omsg + "\n")
        v4(omsg)

    fh.flush()
    return fh


def find_new_sky_range(infiles):
    """Given a list of files, check to see if the SKY
    range is the same for each file. The return value is
    (xrange, yrange),
    where the ranges are either None, if the range does
    not need to be updated, or the (min,max) values for
    that column.
    """

    xlo = []
    xhi = []
    ylo = []
    yhi = []
    for infile in infiles:
        v3("Checking SKY range of {}".format(infile))
        bl = cxcdm.dmTableOpen(infile)
        try:
            x = cw.open_column(bl, "x", infile)
            y = cw.open_column(bl, "y", infile)

            (x1, x2) = cxcdm.dmDescriptorGetRange(x)
            v3(" . x range = {} to {}".format(x1, x2))
            (y1, y2) = cxcdm.dmDescriptorGetRange(y)
            v3(" . y range = {} to {}".format(y1, y2))

            xlo.append(x1)
            ylo.append(y1)
            xhi.append(x2)
            yhi.append(y2)

        finally:
            cxcdm.dmTableClose(bl)

    xlo = np.asarray(xlo)
    xhi = np.asarray(xhi)
    ylo = np.asarray(ylo)
    yhi = np.asarray(yhi)

    if np.unique(xlo).size == 1 and np.unique(xhi).size == 1:
        xr = None
    else:
        xr = (xlo.min(), xhi.max())

    if np.unique(ylo).size == 1 and np.unique(yhi).size == 1:
        yr = None
    else:
        yr = (ylo.min(), yhi.max())

    return (xr, yr)


def _normalize_range(lo, hi):
    "Normalize range to 'nearest' 0.5; assume that lo/hi are numpy values"

    bval = np.floor(lo)
    if lo - bval >= 0.5:
        nlo = bval + 0.5
    else:
        nlo = bval - 0.5

    nlo = nlo.astype(lo.dtype)

    bval = np.floor(hi)
    if hi - bval > 0.5:
        nhi = bval + 1.5
    else:
        nhi = bval + 0.5

    nhi = nhi.astype(hi.dtype)

    return (nlo, nhi)


def update_sky_range(infiles, xr, yr,
                     tmpdir="/tmp"):
    """Update the X and/or Y ranges in infiles
    to match xr/yr, which are either None (for
    no change) or a (lo,hi) tuple.

    The files are changed in place (no change is made if
    both xr and yr are None).

    Ranges are rounded to the lower/higher x.5 value - so
    a range of (-123.6, 235.9) will be written out as
    -124.5 to 236.5.
    """

    if xr is None and yr is None:
        return

    if xr is not None:
        (xlo, xhi) = xr
        (a, b) = _normalize_range(xlo, xhi)
        if (a != xlo) or (b != xhi):
            v3("Converting x range from {}:{} to {}:{}".format(xlo, xhi, a, b))
            xr = (a, b)

    if yr is not None:
        (ylo, yhi) = yr
        (a, b) = _normalize_range(ylo, yhi)
        if (a != ylo) or (b != yhi):
            v3("Converting y range from {}:{} to {}:{}".format(ylo, yhi, a, b))
            yr = (a, b)

    for infile in infiles:
        v3("Updating SKY range of {} to x={} y={}".format(infile, xr, yr))

        bl = cxcdm.dmTableOpen(infile, update=True)
        try:
            if xr is not None:
                v3('Updating x column')
                xcol = cw.open_column(bl, 'x', infile)
                cxcdm.dmDescriptorSetRange(xcol, xr[0], xr[1])
                xcol = None

            if yr is not None:
                v3('Updating y column')
                ycol = cw.open_column(bl, 'y', infile)
                cxcdm.dmDescriptorSetRange(ycol, yr[0], yr[1])
                ycol = None

        finally:
            cxcdm.dmTableClose(bl)


def validate_obsinfo(infiles, colcheck=True):
    """Perform a number of checks and set ups based on the infiles
    parameter:

      - converts from a stack and expand out any directories

      - ensures all files can be read in and removes any with no
        data (assumed to be due to an over-zealous DM filter) or
        that are CC mode.

      - Ensures that each file has
        TIME, CHIP, DET, CCD_ID/CHIP_ID, ENERGY (ACIS only), and
        SKY columns and INSTRUME, DETNAM, TSTART and OBS_ID keywords.

      - ensure OBS_ID values are unique (skip any that are already
        known, supporting interleaved mode) and skip any with OBS_ID ==
        "merged" (case insensitive)

      - reads in the headers

      - checks all files have the same INSTRUME

      - checks that DETNAM is the same for INSTRUME=HRC since
        we do not support combining HRC-I and HRC-S data

      - check that all ACIS files have a READMODE keyword
        and skip CC mode data

      - sorts the data by TSTART

    If colcheck is True (the default) then the files are also checked
    to ensure that they contain the same columns as the first
    "valid" file; any that do not are skipped.

    An error is raised if no files match the filtering.

    Once the files have been sorted, we

      - find the aim-point ccd (by using the first GTI block)
        ACIS only

      - check to see if there are any "multi-OBI observations" and,
        if so, set the ObsId object for the relevant observations
        to include the OBI when converting to a string

    The return value is a list of
    ciao_contrib._tools.obsinfo.ObsInfo objects

    """

    if infiles.strip() == "":
        raise IOError("The infiles parameter is empty.")

    sinfiles = fileio.expand_evtfiles_stack(infiles)
    norig = len(sinfiles)
    if norig == 0:
        raise IOError("No valid event files were found.")
    elif norig == 1:
        # TODO: does it make sense to allow only one observation here?
        v1("Verifying one observation.")
    else:
        v1("Verifying {} observations.".format(norig))

    acols = set(['TIME', 'CHIP', 'DET', 'SKY', 'CCD_ID', 'ENERGY'])
    hcols = set(['TIME', 'CHIP', 'DET', 'SKY', 'CHIP_ID'])
    req_columns = {'ACIS': acols, 'HRC': hcols}

    obsinfos = []
    instrument = None
    detname = None
    blank_line = False

    # Check for multiple obsids in the input set. Note that this checks for
    # the "unique" combination of (obsid, cycle, obi), or - rather -
    # whatever the ObsId object uses for equality (i.e it is not just the
    # value of the OBS_ID keyword).
    #
    obsids = {}

    for infile in sinfiles:
        v3("Checking input file: " + infile)
        try:
            obs = ObsInfo(infile)
        except Exception as exc:
            # With the move to the obsinfo we have lost the specific
            # messages about why a file is skipped, but the information
            # should hopefully still be provided to the user.
            # v1("Skipping {}: {}".format(infile, exc))
            v1("Skipping file: {}".format(exc))
            blank_line = True
            continue

        if obs.nrows < 1:
            v1("Skipping {} as it contains no data.".format(infile))
            blank_line = True
            continue

        # The following is trying to be too clever,
        # in that the expected behavior is to raise the error.
        try:
            v1("Skipping {} as both it and {} have OBS_ID={}.".format(infile, obsids[obs.obsid], obs.obsid))
            blank_line = True
            continue
        except KeyError:
            obsids[obs.obsid] = infile

        if len(obsinfos) == 1:
            filelabel = "file is"
        else:
            filelabel = "files are"

        if instrument is None:
            instrument = obs.instrument
            # The following check should not be needed, since ObsInfo will have
            # already made it, but check again, just in case there are future
            # code changes.
            try:
                rcols = req_columns[instrument]
            except KeyError:
                v1("Skipping {} as INSTRUME={} is unsupported.".format(infile, instrument))
                blank_line = True
                continue

        elif instrument != obs.instrument:
            v1("Skipping {} as it has INSTRUME={} but previous {} for {}".format(infile, obs.instrument, filelabel, instrument))
            blank_line = True
            continue

        if instrument == "ACIS":
            keys = obs.get_header()
            try:
                readmode = keys['READMODE']
            except KeyError:
                v1("Skipping {} as it has no READMODE keyword.".format(infile))
                blank_line = True
                continue

            if readmode == 'CONTINUOUS':
                v1("Skipping {} as it is a CC-mode observation.".format(infile))
                blank_line = True
                continue

        elif instrument == "HRC":
            if detname is None:
                detname = obs.detector
            elif detname != obs.detector:
                v1("Skipping {} as it has DETNAM={} but previous {} for {}".format(infile, obs.detector, filelabel, detname))
                blank_line = True
                continue

        got_columns = obs.get_colnames()
        v2("Found columns {} against {}".format(' '.join(got_columns), ' '.join(rcols)))

        missing_columns = rcols.difference(got_columns)
        nmiss = len(missing_columns)
        if colcheck and nmiss != 0:
            cnames = ' '.join(missing_columns)
            if nmiss == 1:
                v1("Skipping {} as it is missing the {} column".format(infile, cnames))
            else:
                v1("Skipping {} as it is missing columns: {}".format(infile, cnames))

            blank_line = True
            continue

        # Sort primary second, secondary (longer) first, HRC is None.
        sort_order = { 'P' : 2, 'S' : 1, None: 0 }

        sort_tag = sort_order[obs.obsid.cycle]
        time_tag= (obs.tstart,sort_tag) # tuples sort too
        obsinfos.append((time_tag, obs))

    ninfiles = len(obsinfos)
    if ninfiles == 0:
        raise IOError("No valid event files were found.")

    # Now do a multi-obi/interleaved check
    #
    v3("Looking for interleaved/multi-OBI datasets")
    nobsids = {}
    for oi in obsinfos:
        obsidval = oi[1].obsid.obsid
        try:
            nobsids[obsidval] += 1
        except KeyError:
            nobsids[obsidval] = 1

    multis = [k for (k, v) in nobsids.items() if v > 1]
    if len(multis) > 0:
        v3("Found interleaved/multi-OBI ObsIds: {}".format(multis))
        if len(multis) == 1:
            v1("Found one interleaved/multi-OBI observation:")
        else:
            v1("Found {} interleaved/multi-OBI observations:".format(len(multis)))

        # check for interleaved observations; remove them from the 'multis'
        # multi-obi list
        obs_cycle = {}
        for oi in list(obsinfos):
            obsinfo = oi[1]
            obsid = obsinfo.obsid

            if obsid.obsid in multis:
                try:
                    obs_cycle[obsid.obsid] += obsid.cycle
                except KeyError:
                    obs_cycle[obsid.obsid] = obsid.cycle
                except TypeError:
                    continue

        for obsid in obs_cycle.keys():
            # if ObsID has both cycle=P and cycle=S files, then remove it
            # from the multi-obi list
            if obs_cycle[obsid] in ["PS", "SP"]:
                v3("ObsID {} is an interleaved observation".format(obsid))
                multis.remove(obsid)

        # Mark the observations as being "multi obi"
        # and remove any such observation which has no
        # OBI field (by this point we know there are no
        # observations with the same OBI value for a given
        # OBS_ID).
        #
        for oi in list(obsinfos):
            obsinfo = oi[1]
            obsid = obsinfo.obsid
            if obsid.obsid in multis:
                v3("Setting {} as multi-OBI".format(obsinfo))
                try:
                    obsid.is_multi_obi = True
                    v1("  - using label {}".format(obsid))
                except ValueError as ve:
                    # oops, this has no OBI value so should be rejected
                    fname = obsinfo.get_evtfile()
                    v1("Skipping {} as it has no OBI_NUM keyword".format(fname))

                    # as a debug aid
                    v3(str(ve))
                    obsinfos.remove(oi)

    else:
        v3("No interleaved/multi-OBI datasets found")

    # the obsinfos array can be shortened by the above, so re-compute.
    ninfiles = len(obsinfos)
    if ninfiles == 0:
        raise IOError("No valid event files were found.")

    nskip = norig - ninfiles
    if nskip == 1:
        v1("Skipped one observation.")
    elif nskip > 1:
        v1("Skipped {} observations.".format(nskip))

    v3("Time sorting {} observations.".format(ninfiles))
    obsinfos.sort(key=lambda item: item[0])
    out = list(zip(*obsinfos))

    if blank_line:
        v1("")

    return list(out[1])


def obsinfo_checks(obsinfos):
    """Check that the observations do not contain any known issues.

    At present this is HRC-only, and checks that the ranges of the PI
    columns match. If they don't then a warning message is displayed,
    and also returned for display at the end of the program.

    An empty list is returned if there are no warnings.
    """

    warn_msgs = []
    if obsinfos[0].instrument != "HRC":
        return warn_msgs

    v3("Verifying if the PI columns in the HRC files have the same meaning.")

    # check to see whether PI ranges are different
    def get_pi_range(cis):
        for cs in cis:
            if cs.name.upper() == 'PI':
                return cs.range

        return None

    pi_ranges = [get_pi_range(obs.get_columns()) for obs in obsinfos]
    v4("PI ranges={}".format(pi_ranges))
    pi_ranges = [pir for pir in pi_ranges if pir is not None]
    if pi_ranges != []:
        pi_flags = [pir != pi_ranges[0] for pir in pi_ranges]
        if any(pi_flags):
            warn_msgs = [
                "WARNING: the PI columns of the event files do not match; please reprocess",
                "         with chandra_repro and re-run this script as combined analysis",
                "         of these files will be difficult.",
                ""]

            for wm in warn_msgs:
                v1(wm)

    return warn_msgs


def find_hrci_backgrounds(obsinfos, bgndmap=None, tmpdir=None):
    """Find the HRC-I background files for each of the observations;
    it is assumed that the data is for HRC-I observations and than
    background-subtraction has been selected.

    The return value is

       None if no observations have a background file, so
              we are to act as if background=none

       a list of background files (elements are None if that
              observation has no background file)

    Screen messages are displayed to inform the user what is going on.

    If bgndmap is not None then it should be a dictionary, mapping
    between the event file name (as given by the user to the script)
    to the background file to use. This is used instead of the CALDB
    query. Note that the restriction to the basename of the event file
    means that a user can not use a structure such as
    <obsid>/evt2.fits, but for now this is okay since this is a
    special case for testing/development.
    """

    bgfiles = []
    missing = []
    for obs in obsinfos:
        bfile = fi.find_blanksky_hrci(obs, verbose=False,
                                      bgndmap=bgndmap, tmpdir=tmpdir)
        if bfile is None:
            missing.append(obs.get_evtfile())

        bgfiles.append(bfile)

    nmissing = len(missing)
    if nmissing == len(obsinfos):
        v1("No HRC-I background files are found; setting background=none.\n")
        return None

    if nmissing == 1:
        v1("Skipping {} as it has no matching HRC-I background file.".format(missing[0]))
        v1("Set background=none to turn off the background subtraction and include this file.")
        return bgfiles

    elif nmissing > 1:
        v1("Skipping the following as they have no matching HRC-I background file.")
        for mfile in missing:
            v1("    " + mfile)

        v1("Set background=none to turn off the background subtraction and include these files.")

    return bgfiles


def merge_event_files(infiles,
                      outfile,
                      obsinfos=None,
                      colfilter=False,
                      lookupTab=None,
                      asolfile='Merged',
                      bpixfile='Merged',
                      dtffile='Merged',
                      maskfile='Merged',
                      tmpdir="/tmp",
                      clobber=False,
                      verbose=0):
    """Merge together infiles and - if colfilter is True and obsinfos
    is not None, exclude
    columns that do not match - as well as the lookup table, to create
    outfile. colinfo is expected to match that from
    fileio.get_keys_cols_from_file().

    An attempt is made to ensure that there is only one GTI block
    per CCD, but this is not guaranteed to work in all cases.

    The lookup table rules are modified by the header values
    to try and reduce screen output if lookuptab and
    headers are not None.

    The header keywords ASOLFILE, BPIXFILE, DTFFILE, MASKFILE,
    are set to the given value if the keywords are
    not set to None. The default value is the string "Merged".

    The merge always removes the following columns:

        PHAS

    The merge always removes the subspace for the following columns:

      ACIS:

        PHAS
        EXPNO

      HRC:
        CLKTICKS - fixes in DS8.5 may lead to problems when combining
                   with earlier data (e.g. DS8.4.5 which was used for
                   roughly half of Repro 4 L0 processing)
        AV1      - ditto
        AU1      - ditto

        MJF      - can have different subspaces
        MNF      - ditto
        ENDMNF   - ditto
        SUB_MJF  - ditto

    since they can lead to multiple GTI components, as they can differ
    between ObsIds, or - in the case of PHAS - can lead to large file
    sizes and may not have the same format across the files
    (e.g. VFAINT vs FAINT mode).

    If only one file is input then dmmerge is still run.

    *** Special treatment ***

    For HRC data the routine checks that the PI columns all have the same
    range and, if not, removes it. This is because old/un-reprocessed
    data can have a PI range of 0:255 rather than the 'modern' range of
    0:1023. This check *could* be applied to other columns, but this
    is not done at present (for instance the TIME and SKY columns are
    expected to have different ranges). To avoid having a GTI_CPT2
    block the merge creates a temporary file which is then copied
    to remove the PI subspace.

    The support for PBKFILES was removed in CIAO 4.6.
    """

    nfiles = len(infiles)
    if nfiles == 1:
        v1("Copying reprojected events file to " + outfile)
    else:
        v1("Merging reprojected events files to " + outfile)

    v3(" ... using lookup table: {}".format(lookupTab))

    # We can reduce the history record (and the argument length to
    # dmmerge) if we know the instrument type: at present we only
    # care about ACIS vs HRC
    #
    try:
        inst = obsinfos[0].instrument
        if inst not in ['ACIS', 'HRC']:
            raise TypeError("Hack to break out of the loop")

        v4(" ... using instrument = {} to specialize subspace rules".format(inst))

    except TypeError:
        v4("No obs info included, so can not specialize subspace rules when merging.")
        inst = None

    (xr, yr) = find_new_sky_range(infiles)
    update_sky_range(infiles, xr, yr, tmpdir=tmpdir)

    hrc_pi_case = False

    if inst is None or inst == 'ACIS':
        excl_cols = set(["phas"])
    else:
        excl_cols = set()

    if colfilter and obsinfos is not None:
        v3(" ... checking the columns match")

        cols = dict([(ci.name, ci) for ci in obsinfos[0].get_columns()])
        cmatch = dict([(ci.name, 1) for ci in obsinfos[0].get_columns()])

        for obs in obsinfos[1:]:
            for ci in obs.get_columns():
                if ci.name in excl_cols:
                    continue

                try:
                    ci0 = cols[ci.name]
                except KeyError:
                    excl_cols.add(ci.name)
                    continue

                if (ci.type != ci0.type) or (ci.dims != ci0.dims):
                    excl_cols.add(ci.name)
                    continue

                # Special case HRC/PI check; only report the first time
                # we see this
                if inst == 'HRC' and ci.name.upper() == 'PI' and \
                   not hrc_pi_case and ci.range != ci0.range:
                    v1("WARNING: dropping the PI column from the merged " +
                       "event file.")
                    v2("         PI ranges = " +
                       "{} vs {}".format(ci0.range, ci.range))
                    hrc_pi_case = True
                    excl_cols.add(ci.name)
                    continue

                cmatch[ci.name] += 1

        for (cname, nfound) in cmatch.items():
            if nfound != nfiles:
                excl_cols.add(cname)

        v3(" ... and removing {}".format([' '.join([exc for exc in excl_cols])]))

        # dmmerge needs the same column order in all the files, so use
        # the ordering of the first file.
        colfilter = []
        for ci in obsinfos[0].get_columns():
            if ci.name in excl_cols:
                continue
            colfilter.append(ci.name)

        if colfilter == []:
            raise IOError("Unable to find any common columns in the input files to merge!")

        # We could try and be clever and switch to 'cols -xxx,-yyy' when
        # it is smaller, which would also require that the column order is
        # the same in all the files. This is a little bit messy to get right,
        # so leave as is for the moment.
        #
        colfilter = "[cols {}]".format(','.join(colfilter))

    elif inst == 'ACIS':
        colfilter = "[cols -phas]"

    else:
        colfilter = ""

    # We may not remove these columns, but we do want to ensure the subspace
    # is removed.
    #
    excl_subspace_acis = ["expno"]
    excl_subspace_hrc = ["clkticks", "av1", "au1", "mjf", "mnf",
                         "endmnf", "sub_mjf"]

    if inst == 'ACIS':
        excl_subspace = excl_subspace_acis
    elif inst == 'HRC':
        excl_subspace = excl_subspace_hrc
    else:
        excl_subspace = excl_subspace_acis + excl_subspace_hrc

    v4("  ... excluding subspace: {}".format(excl_subspace))
    for colname in excl_subspace:
        excl_cols.add(colname)

    subspacefilter = ",".join(["-" + colname for colname in excl_cols])

    if lookupTab is not None and obsinfos is not None:
        v3(" ... and modifying the lookup table")
        newtab = create_lookup_table(lookupTab, obsinfos, tmpdir=tmpdir)
        ltab = newtab.name
    else:
        ltab = lookupTab

    v3("Column filter for merge: {}".format(colfilter))
    v3("Subspace filter for merge: {}".format(subspacefilter))

    # If we are removing the PI column from HRC data then the
    # merge is to a temporary file so that we can then have a
    # separate dmcopy with "[subspace -pi]". The merge clears
    # out the column (and hence the TLMIN/MAX values) and the
    # dmcopy - which has to be separate - the subspace for the
    # column. Note that the "-pi" element in subspacefilter
    # does nothing but kept in as no point in removing.
    #
    if hrc_pi_case:
        merge_outfile_temp = tempfile.NamedTemporaryFile(dir=tmpdir,
                                                         suffix=".merged")
        merge_outfile = merge_outfile_temp.name
        clobber_merge = True
        v3("Merge to temporary file: {}".format(merge_outfile))
    else:
        merge_outfile = outfile
        clobber_merge = clobber

    stkfile = make_stackfile(infiles, dir=tmpdir, suffix=".merge")
    try:
        run.dmmerge("@{}{}[subspace {}]".format(stkfile.name,
                                                colfilter,
                                                subspacefilter),
                    merge_outfile,
                    clobber=clobber_merge,
                    verbose=verbose,
                    lookupTab=ltab,
                    skyupdate=True
                    )

    finally:
        stkfile.close()

    if hrc_pi_case:
        v3("dmcopy the merged event file to remove PI subspace")
        run.dmcopy(merge_outfile + "[subspace -pi]",
                   outfile,
                   option="all",  # should not be necessary, but kept in
                   clobber=clobber)
        merge_outfile_temp = None

    # Edit keywords after the merge
    edits = []
    keydict = fileio.get_keys_from_file(outfile)

    def add_edit(name, val):
        if val is None:
            return

        try:
            keydict[name]
        except KeyError:
            return

        # could check whether the keyword needs changing
        # but not really worth it

        if val.find('/') != -1:
            val = "'{}'".format(val)

        action = "{} = {}".format(name, val)
        edits.append(action)

    add_edit("ASOLFILE", asolfile)
    add_edit("BPIXFILE", bpixfile)
    add_edit("DTFFILE", dtffile)
    add_edit("MASKFILE", maskfile)

    if edits == []:
        v3("No ancillary file keywords to edit in {}".format(outfile))
        return

    v3("Editing ancillary file keywords in {}".format(outfile))
    tfile = tempfile.NamedTemporaryFile(dir=tmpdir, mode='w+',
                                        suffix=".dmhedit")
    tfile.write('#add\n')
    tfile.write('\n'.join(edits))
    tfile.write('\n')
    tfile.flush()
    run.dmhedit_file(outfile, tfile.name)


def process_reference_position(refpos, obsinfos):
    """If refpos is given, extract the reference position from it,
    otherwise use the tangent points of the observations to calculate a
    "mean" location.

    The return value is the tuple
        (refcoordval, ra, dec)
    where refcoordval can be a file name or a space-separated string.
    """

    rpos = utils.parse_refpos(refpos)
    rval = None
    if rpos is None:
        v1("Calculating new tangent point.")
        tpts = [obs.tangentpoint for obs in obsinfos]
        (ras, decs) = list(zip(*tpts))
        (ra, dec) = coords.utils.calculate_nominal_position(list(ras),
                                                            list(decs))

    elif rpos[2] is not None:
        v1("Tangent point is taken from the file {}".format(rpos[2]))
        try:
            (ra, dec) = fileio.get_tangent_point(rpos[2])

        except IOError as ioe:
            # could look for RA_NOM/DEC_NOM as a fall back but doubt it is
            # worth it.
            v2("Error is: {}".format(ioe))
            raise ValueError("Unable to find a tangent position in " +
                             "{}".format(rpos[2]))

        rval = rpos[2]

    else:
        ra = rpos[0]
        dec = rpos[1]

    # reproject_events doesn't like negative-valued RA
    # so just in case
    if ra < 0:
        ra += 360.0

    rastr = coords.format.deg2ra(ra, 'hms', ndp=3)
    decstr = coords.format.deg2dec(dec, 'dms', ndp=2)
    v1(f"New tangent point: RA={rastr} Dec={decstr}")

    if rval is None:
        rval = "{0} {1}".format(ra, dec)

    return (rval, ra, dec)


def list_observations(instrume, ranom, decnom, obsinfos):
    """Write to screen a summary of the observations
    that are to be combined. ra and dec give the position
    of the combined nominal position for the data (in
    degrees).

    It also notes values that are different but are not listed in
    the observation table:

        EXPTIME DATAMODE SIM_X GRATING
        CTI_CORR EXPTIME READMODE for ACIS

    The return value is a list of those keywords that differ sufficiently
    such that the merged event file should not be used directly for
    analysis (e.g. spectral extraction). This list can
    be empty. The elements of the list are tuples of the form

        (keyword, max-permisible-difference, actual-difference)
        (keyword, list-of-values-that-are-used)

    depending on what the check is (e.g. numeric vs string).

    A return of [] does not mean that the merged event file can be safely
    used since the current checks are not guaranteed to be exhaustive.

    Note that this routine will error out if any of the input files
    are missing one of the checked-for keys. This means that
    Marx data is likely to fall over because it is missing
    keys like RAND_PI. Should we try and support such files?
    """

    nobs = len(obsinfos)
    nchar = np.floor(np.log10(nobs)).astype(np.int) + 1

    if nobs == 1:
        suffix = ''
    else:
        suffix = 's'
    v1("\nObservation{} to be reprojected:\n".format(suffix))

    # Check for any multi-obi datasets, as this increases the ObsId field
    # width. For ACIS datasets this can get further increased if there
    # are any interleaved-mode datasets (see later)
    #
    mo = [obs for obs in obsinfos if obs.obsid.is_multi_obi]
    if mo == []:
        olen = 5
    else:
        olen = 9

    # For ACIS we include the FP_TEMP value; unless this gets more complicated
    # it is not worth avoiding the code duplication (at this time)
    #
    # Note that the width allocated to DETNAM differs.
    #
    if instrume == "ACIS":
        # Do we need to allocate more space for interleaved-mode data?
        obsids = [obs.obsid for obs in obsinfos]
        if not all([obsid.cycle is None for obsid in obsids]):
            olen += 2

        fmt = "{:" + str(nchar) + "} {:^" + str(olen) + \
              "} {:^10} {:^5} {:^11} {:^8} {:^5} {:^5} {:^5}"
        v1(fmt.format("", "Obsid", "Obs Date", "Exp", "DETNAM",
                      "SIM_Z", "FP", "Sepn", "PA"))
        hdr = fmt.format("", "", "", "(ks)", "", "(mm)", "(K)", "(')", "(deg)")
        fmts = ["{:" + str(nchar) + "}", "{:" + str(olen) + "s}",
                "{:10s}", "{:5.1f}", "{:11s}", "{:8.3f}", "{:5.1f}",
                "{:5.1f}", "{:+5.0f}"]
        arraynames = ['RA_NOM', 'DEC_NOM', 'ROLL_NOM', 'FP_TEMP',
                      'SIM_X', 'SIM_Y', 'SIM_Z']

    else:
        fmt = "{:" + str(nchar) + "} {:^" + str(olen) + \
              "} {:^10} {:^5} {:^6} {:^8} {:^5} {:^5}"
        v1(fmt.format("", "Obsid", "Obs Date", "Exp", "DETNAM", "SIM_Z",
                      "Sepn", "PA"))
        hdr = fmt.format("", "", "", "(ks)", "", "(mm)", "(')", "(deg)")
        fmts = ["{:" + str(nchar) + "}", "{:" + str(olen) + "s}",
                "{:10s}", "{:5.1f}", "{:6s}", "{:8.3f}", "{:5.1f}", "{:+5.0f}"]
        arraynames = ['RA_NOM', 'DEC_NOM', 'ROLL_NOM',
                      'SIM_X', 'SIM_Y', 'SIM_Z']

    arrayvals = [[] for n in arraynames]

    v1(hdr)
    v1('-' * len(hdr))

    d2r = coords.utils.degtorad
    r2d = coords.utils.radtodeg
    s2c = coords.utils.spherical_to_cartesian
    angsep = coords.utils.angular_separation
    bearing = coords.utils.bearing

    anom = d2r(ranom)
    bnom = d2r(decnom)
    vv0 = s2c(anom, bnom)

    checks = {}

    def addit(obsid, key, value):
        """Add obsid to the store for the keyword key
        with the given value."""

        checks.setdefault(key, {})
        try:
            checks[key][value].append(obsid)
        except KeyError:
            checks[key][value] = [obsid]

    def addkey(obsid, hdr, key):
        try:
            addit(obsid, key, hdr[key])
        except KeyError:
            pass

    if instrume == 'ACIS':
        for key in ['RAND_PI', 'READMODE', 'EXPTIME']:
            arrayvals.append([])
            arraynames.append(key)

    # add keywords to the list of values that are considered
    # "warnings"
    #
    for key in ['GRATING', 'DETNAM']:
        arrayvals.append([])
        arraynames.append(key)

    for (ctr, obs) in zip(range(1, nobs + 1), obsinfos):

        obsid = obs.obsid
        hdr = obs.get_header()
        try:
            addkey(obsid, hdr, 'DATAMODE')
            addkey(obsid, hdr, 'GRATING')
            if instrume == 'ACIS':
                addkey(obsid, hdr, 'EXPTIME')
                # this probably needs more smarts (CTI_CORR setting)
                addkey(obsid, hdr, 'CTI_CORR')
                addkey(obsid, hdr, 'READMODE')

            addkey(obsid, hdr, 'SIM_X')     # ditto
            addkey(obsid, hdr, 'SIM_Y')     # ditto

            for (a, k) in zip(arrayvals, arraynames):
                a.append(hdr[k])

            # How best to describe close, but not identical, observations?
            ra = d2r(hdr['RA_NOM'])
            dec = d2r(hdr['DEC_NOM'])
            vv = s2c(ra, dec)
            asep = r2d(angsep(vv, vv0)) * 60.0

            if asep == 0.0:
                pa = 0.0
                tmpfmts = fmts[:]

            else:
                pa = r2d(bearing(anom, bnom, ra, dec))
                if asep < 0.05:
                    tmpfmts = fmts[:]
                    asep = "< 3\""
                    tmpfmts[-2] = "{:>5s}"
                else:
                    tmpfmts = fmts[:]

            fmtargs = [ctr,
                       str(obsid),
                       hdr['DATE-OBS'][:10],
                       hdr['EXPOSURE'] / 1000.0,
                       hdr['DETNAM'],
                       hdr['SIM_Z'],
                       asep,
                       pa
                       ]
            if instrume == "ACIS":
                fmtargs.insert(6, hdr['FP_TEMP'])

            fmt = " ".join(tmpfmts)
            v1(fmt.format(*fmtargs))

        except KeyError as ke:
            raise ValueError("ObsId {} ({}) is missing the {} keyword.".format(obsid, obs.get_evtfile(), ke))

    v1("")

    # Try and make the display "readable", even if it makes the code
    # somewhat messy and full of heuristics.
    #
    for (keyname, values) in checks.items():
        if len(values) < 2:
            continue

        v1("WARNING - {} values differ:".format(keyname))
        out = [(len(value), key, value)
               for (key, value) in values.items()]
        out.sort(reverse=True)
        if len(out) == 2:
            larger = out[0]
            smaller = out[1]
            nsmaller = smaller[0]
            nlarger = larger[0]

            if nlarger == 1:
                lbl = "{} has".format(larger[2][0])
            else:
                lbl = "the rest have"

            if nsmaller == 1:
                v1("  Obsid {} has {}={} and {} {}".format(smaller[2][0], keyname, smaller[1], lbl, larger[1]))
            elif nsmaller < 6:
                v1("  Obsids {} have {}={} and {} {}".format(" ".join([str(s) for s in smaller[2]]), keyname, smaller[1], lbl, larger[1]))
            else:
                v1("  {} Obsids have {}={} and {} {}".format(nsmaller, keyname, smaller[1], lbl, larger[1]))

        else:
            for (nobsids, val, obsids) in out:
                if nobsids == 1:
                    v1("  ObsId {} has {}={}".format(obsids[0], keyname, val))
                elif nobsids < 6:
                    v1("  ObsIds {} have {}={}".format(" ".join([str(o) for o in obsids]), keyname, val))
                else:
                    v1("  {} ObsIds have {}={}".format(nobsids, keyname, val))

        v1("")

    # values taken from dmmerge_header_lookup.txt
    arraydeltas = {'RA_NOM': 0.0003, 'DEC_NOM': 0.0003, 'ROLL_NOM': 1.0,
                   'FP_TEMP': 2.0,
                   'SIM_X': 0.001, 'SIM_Y': 0.001, 'SIM_Z': 0.1,
                   'RAND_PI': 0.05}

    # Create any warnings to display at the end of the script (this does
    # really repeat some of the other checks but we have not decided what
    # information is best to present to the user).
    #
    warnings = []
    for (a, k) in zip(arrayvals, arraynames):

        if k == 'EXPTIME':
            # treat as string as want to see different values
            aa = np.asarray([str(x) for x in a])
        else:
            aa = np.asarray(a)

        try:
            delta = aa.ptp()
        except TypeError:
            # assume a string
            uvals = np.unique(aa)
            if len(uvals) != 1:
                warnings.append((k, uvals))

            continue

        mdelta = arraydeltas[k]
        if delta > mdelta:
            warnings.append((k, mdelta, delta))

    return warnings


def number_decimal_places(x):
    """Return the number of decimal places in the value.

    There's probably a more-standardised way of doing this.

    Parameters
    ----------
    x : value
        The value

    Returns
    -------
    ndp : int
        The number of decimal places in x (can be 0).
    """

    xs = str(x)
    decimal = xs.find('.')
    if decimal == -1:
        return 0

    return len(xs) - decimal - 1


def display_merging_warnings(warnings, evtfile, obsinfos):
    """Display any warnings about the use of the merged event
    file (evtfile) with the 'response' tools.

    warnings is the output of list_observations.
    """

    # Skip any DETNAM differences.
    warnings = [w for w in warnings if w[0] != 'DETNAM']

    # Note that aimpoint is None for HRC data. For now assume that
    # we do not have to report on mixed-instrument data (i.e. HRC and
    # ACIS), so do not need to worry about some aimpoints being
    # defined and some not.
    #
    aimpoints = np.unique(np.asarray([obs.aimpoint for obs in obsinfos
                                      if obs.aimpoint is not None]))

    if warnings == [] and len(aimpoints) < 2:
        return

    # I worry about displaying the max limits, since at some level they are
    # arbitrary, but I feel we need to display something so that a user can
    # say (of it varies by x but that is only just over the limit so I'll
    # ignore the warning).
    #
    # The handling of keywords here is beginning to get a bit special-cased
    # and not generic/clean.
    #
    v1(f"Warning: the merged event file {evtfile}")
    v1("   should not be used to create ARF/RMF/exposure maps because")
    spacer = "      "
    for warnvals in warnings:
        if len(warnvals) == 3:
            (key, mdiff, diff) = warnvals

            # Restrict the difference to the number of decimal places
            # of the limit (mdiff). Assumption is that mdiff is positive.
            #
            ndp = number_decimal_places(mdiff)
            if ndp > 0:
                fmt = "{{:.{}f}}".format(ndp)
                diff = fmt.format(diff)

            msg = f"{spacer}the {key} keyword varies by {diff} " + \
                f"(limit is {mdiff})"
            v1(msg)

        elif len(warnvals) == 2:
            (key, diffvals) = warnvals
            msg = f"{spacer}the {key} keyword contains: {' '.join(diffvals)}"
            v1(msg)

            if key == "EXPTIME":
                v1(f"{spacer}  which means that the DTCOR value, " +
                   "and hence LIVETIME/EXPOSURE")
                v1(f"{spacer}  keywords are wrong")

        else:
            v1(f"{spacer}[internal error] unrecognized warning {warnvals}")

    if len(aimpoints) > 1:
        v1("{}the aim points fall on CCDs: {}".format(spacer, ' '.join([str(a) for a in aimpoints])))
        v1(f"{spacer}  which means that the ONTIME/LIVETIME/EXPOSURE keywords")
        v1(f"{spacer}  do not reflect the full observation length.")

    v1("")


def setup_obsid_asol(obsinfos, asolfiles):
    """asolfiles is the user input; if it is empty then verify that we
    can find aspect solutions for each of the observations from their
    headers. If given a list of names, perhaps as a stack, then match
    them up and set each observation to use the relevant file(s).

    IOError is raised if a file can not be found.
    """

    if asolfiles.strip() == "":
        missing = []
        for obs in obsinfos:
            if obs.get_asol_() is None:
                missing.append(obs.get_evtfile())

        nmissing = len(missing)
        if nmissing == 1:
            raise IOError("Missing the asol file(s) for " +
                          "{}.".format(missing[0]))

        elif nmissing > 1:
            indent = "\n    "
            raise IOError("Missing the asol files for {} observations:{}{}".format(nmissing, indent, indent.join(missing)))

    else:
        asol = stk.build(asolfiles)
        asol = match_obsid_asol(obsinfos, asol)
        for (obs, asols) in zip(obsinfos, asol):
            obs.set_asol(asols)


def setup_obsid_bpix(obsinfos, badpixfiles):
    """badpixfiles is the user input; if it is empty then verify that
    we can find a bad-pixel file for each of the observations from
    their headers. If given a list of names, perhaps as a stack, then
    match them up and set each observation to use the relevant
    file(s).

    IOError is raised if a file can not be found.
    """

    nobs = len(obsinfos)
    if badpixfiles.lower() == 'none':
        for obs in obsinfos:
            obs.set_ancillary('bpix', 'NONE')

    elif badpixfiles.lower() == 'caldb':
        for obs in obsinfos:
            obs.set_ancillary('bpix', 'CALDB')

    elif badpixfiles.strip() == "":
        missing = []
        for obs in obsinfos:
            if obs.get_ancillary_('bpix') is None:
                missing.append(obs.get_evtfile())

        nmissing = len(missing)
        if nmissing == nobs:
            v1("WARNING - no bad-pixel files were found, setting badpixfiles=CALDB.")
            for obs in obsinfos:
                obs.set_ancillary('bpix', 'CALDB')

        elif nmissing == 1:
            raise IOError("Missing the bad-pixel file for {}.".format(missing[0]))

        elif nmissing > 1:
            indent = "\n    "
            raise IOError("Missing bad-pixel files for {} observations:{}{}".format(nmissing, indent, indent.join(missing)))

    else:
        badpix = stk.build(badpixfiles)

        # ARDLIB does not check for the presence of a *.gz version if the
        # original file does not exist, so need to manually set the correct
        # file name here. For now we do not do this expansion for the
        # other ancillary files as the other parts of CIAO should deal with
        # this automatically.
        #
        out = []
        for bpixfile in badpix:
            if not os.path.isfile(bpixfile):
                bpixfile += ".gz"
                if not os.path.isfile(bpixfile):
                    raise IOError("Unable to find bad pixel file={} (or .gz version)".format(bpixfile[:-3]))

                v3("Found .gz version of badpixfile=" + bpixfile)

            out.append(bpixfile)

        badpix = match_obsid(obsinfos, out, 'bad-pixel')
        nbpix = len(badpix)
        if nbpix != nobs:
            raise ValueError("The number of bad-pixel files ({}) does not match the number of input files ({})".format(nbpix, nobs))

        for (obs, bpix) in zip(obsinfos, badpix):
            obs.set_ancillary('bpix', bpix)


def setup_obsid_ancillary(obsinfos, userinput, anctype, warnmsg):
    """Look at userinput to set the ancillary file type 'anctype'.
    If all files are missing then the file is set to 'NONE' and
    warnmsg is used to tell the user what this means.

    The files are matched to the observations (when given explicitly)
    via the OBS_ID/OBI_NUM keywords in the headers, which will raise
    an IOError if a match can not be made. Prior to CIAO 4.7 there
    was a mode where this check was not made (to support matching PBK
    files but also used - for some reason I'm not quite sure about -
    for DTF files). As we no-longer use PBK files this option has been
    removed.

    This is not meant to be called directly by a user.

    """

    nobs = len(obsinfos)
    if userinput.lower() == 'none':
        for obs in obsinfos:
            obs.set_ancillary(anctype, 'NONE')

    elif userinput.strip() == "":
        missing = []
        for obs in obsinfos:
            if obs.get_ancillary_(anctype) is None:
                missing.append(obs.get_evtfile())

        nmissing = len(missing)
        if nmissing == nobs:
            v1("WARNING - no {0} files were found, setting {0}files=NONE. {1}".format(anctype, warnmsg))
            for obs in obsinfos:
                obs.set_ancillary(anctype, 'NONE')

        elif nmissing == 1:
            raise IOError("Missing the {} file for {}.".format(anctype, missing[0]))

        elif nmissing > 1:
            indent = "\n    "
            raise IOError("Missing {} files for {} observations:{}{}".format(anctype, nmissing, indent, indent.join(missing)))

    else:
        files = stk.build(userinput)
        files = match_obsid(obsinfos, files, anctype)
        nfiles = len(files)
        if nfiles != nobs:
            raise ValueError("The number of {} files ({}) does not match the number of input files ({})".format(anctype, nfiles, nobs))

        for (obs, filename) in zip(obsinfos, files):
            obs.set_ancillary(anctype, filename)


def setup_obsid_mask(obsinfos, maskfiles):
    """maskfiles is the user input; if it is empty then verify that we
    can find the mask file for each of the observations from their
    headers. If given a list of names, perhaps as a stack, then match
    them up and set each observation to use the relevant file(s).

    If a file can not be found then it is either ignored (set to NONE),
    when all such files are missing, or an IOError is raised (when only some
    of the files are missing).
    """

    setup_obsid_ancillary(obsinfos, maskfiles, 'mask',
                          'Invalid data may be used.')


def setup_obsid_dtf(obsinfos, dtffiles):
    """dtffiles is the user input; if it is empty then verify that we
    can find the DTF file for each of the observations from their
    headers. If given a list of names, perhaps as a stack, then match
    them up and set each observation to use the relevant file(s).

    If a file can not be found then it is either ignored (set to NONE),
    when all such files are missing, or an IOError is raised (when only some
    of the files are missing).

    The observations must be for HRC.
    """

    setup_obsid_ancillary(obsinfos, dtffiles, 'dtf',
                          'Exposure duration weighting will not be applied.')


def get_observation_xygrids(obsinfos, binval,
                            tmpdir="/tmp/"):
    """Return an array of AxisGrid objects for the x and y axes representing
    each observation in infiles/hdrs/asolfiles/maskfiles.
    """

    grids = []
    for obs in obsinfos:
        infile = obs.get_evtfile()
        v3("get_observation_xygrids: infile=" + infile)

        # TODO: we know that this is the same for all files
        if obs.instrument == "ACIS":
            chips = fileio.get_ccds(infile)
            lbl = "ccds"
        else:
            chips = fileio.get_chips(infile)
            lbl = "chips"

        # This check should have already been made but just in case
        if chips is None:
            raise IOError("No {} found in {}!".format(lbl, infile))

        v3("get_observation_xygrids: instrument={} chips={}".format(obs.instrument, chips))
        (xg, yg) = fileio.find_output_grid2(obs, binval, chips,
                                            tmpdir=tmpdir)
        v3("get_observation_xygrids: xg={} yg={}".format(xg, yg))

        grids.append((xg, yg))

    return grids


def calculate_output_grid(obs_xygrids,
                          binval,
                          size,
                          instrume,
                          tmpdir="/tmp/"
                          ):
    """Calculate the output grid for the final image. The obs_xygrids
    array is the return value from get_observation_xygrids().

    The return value is an array of (xgrid,yfrid) objects.  At present
    all elements are the same, but this may change.
    """

    ninfiles = len(obs_xygrids)
    v3("calculate_output_grid: combining {} grids".format(ninfiles))
    (xunion, yunion) = obs_xygrids[0]
    for (xg, yg) in obs_xygrids[1:]:
        (xunion, yunion) = (xunion.union(xg), yunion.union(yg))

    v3("calculate_output_grid: union={} {}".format(xunion, yunion))
    (xlo, xhi) = xunion.get_limits()
    (ylo, yhi) = yunion.get_limits()
    v3("calculate_output_grid: limits={}:{} {}:{}".format(xlo, xhi, ylo, yhi))

    if size is not None:

        v3("calculate_output_grid: max grid size = {}".format(size))
        pixsize = max([(xhi - xlo) * 1.0 / size,
                       (yhi - ylo) * 1.0 / size])
        if int(pixsize) == pixsize:
            pixsize = int(pixsize)

        v3("calculate_output_grid: -> pixsize = {}".format(pixsize))
        xrng = AxisRange(xlo, xhi, pixsize)
        yrng = AxisRange(ylo, yhi, pixsize)
        xstr = "{}".format(xrng)
        ystr = "{}".format(yrng)
        nx = xrng.nbins
        ny = yrng.nbins

        xygrids = [(xrng.copy(), yrng.copy()) for i in range(ninfiles)]

    else:
        nx = xunion.nbins
        ny = yunion.nbins
        xstr = "{}".format(xunion)
        ystr = "{}".format(yunion)
        pixsize = xunion.size

        xygrids = [(xunion.copy(), yunion.copy()) for i in range(ninfiles)]

    pixsize = utils.sky_to_arcsec(instrume, pixsize)

    v1("\nThe merged images will have {} by {} pixels, a pixel size of {} arcsec,".format(nx, ny, pixsize))
    v1("    and cover x={}, y={}.".format(xstr, ystr))

    return xygrids


def matchup_xygrids_auto(obsinfos, bin, maxsize,
                         tmpdir="/tmp/"):
    """Return an array of xygrid values for the processing.

    """

    v1("Calculating the output grid")
    instrume = obsinfos[0].instrument
    obs_xygrids = get_observation_xygrids(obsinfos, bin, tmpdir=tmpdir)
    xygrids = calculate_output_grid(obs_xygrids,
                                    bin,
                                    maxsize,
                                    instrume,
                                    tmpdir=tmpdir)

    process = [True] * len(obsinfos)
    obs_xygrids = None

    if instrume == 'ACIS':
        getfunc = fileio.get_ccds
    else:
        getfunc = fileio.get_chips

    chipslist = [getfunc(obs.get_evtfile()) for obs in obsinfos]

    return (xygrids, chipslist, process)


def matchup_xygrids_user(xygrid, obsinfos, binsize, sizes, xrange, yrange,
                         tmpdir="/tmp/"):
    """Return an array of xygrid values for the processing.

    """

    v1("Finding which observations overlap the output grid")
    (nx, ny) = sizes
    (xlo, xhi) = xrange
    (ylo, yhi) = yrange

    # Filter out those observations that do not overlap the
    # output grid. Rather than change each array to remove the
    # un-needed observations, we create a flag array and send
    # that to the necessary routines. Note that the check ensures
    # that at least one chip of an observation overlaps the requested
    # grid.
    #
    (process, chipslist) = which_obsids_overlap(obsinfos,
                                                xlo, ylo, xhi, yhi,
                                                tmpdir=tmpdir
                                                )

    xrng = AxisRange(xlo, xhi, binsize)
    yrng = AxisRange(ylo, yhi, binsize)
    xygrids = [(xrng.copy(), yrng.copy()) for i in range(len(obsinfos))]

    pixsize = utils.sky_to_arcsec(obsinfos[0].instrument, binsize)

    v1("\nThe merged images will have {} by {} pixels, a pixel size of {} arcsec,".format(int(nx), int(ny), pixsize))
    v1("    and cover x={}, y={}.".format(xrng, yrng))

    return (xygrids, chipslist, process)


# The check-using-FOV-overlap code is changeset af3b39bb7cf9
# https://bitbucket.org/doug_burke/ciao-contrib/changeset/af3b39bb7cf9b2d468216196444bc360599e1e96
#
def which_obsids_overlap(obsinfos,
                         xlo, ylo, xhi, yhi,
                         tmpdir="/tmp/"):
    """Returns a boolean array which indicates whether the
    observation overlaps with the user filter - defined by
    the xlo/xhi, ylo/yhi arguments - and an array of ccds that
    overlap this range. The return value is therefore (flags, chiplists)
    where each element of flags is a boolean, and each element of chiplists
    is an array.

    It also informs the user which observation(s) are being excluded.

    The overlap check is based on the events in the input file, rather
    than the FOV file. This means you can lose effective area (e.g.
    when the FOV file and grid just overlap but there are no events
    in the overlap region) but it is unlikely to change results in most
    cases.

    The return raises a ValueError if no observations overlap.
    """

    user_filter = "RECT({},{},{},{})".format(xlo, ylo, xhi, yhi)
    keep = []
    chipslist = []
    skipped_obsids = []

    if obsinfos[0].instrument == 'ACIS':
        getfunc = fileio.get_ccds
    else:
        getfunc = fileio.get_chips

    for obs in obsinfos:
        infile = obs.get_evtfile()
        fname = "{}[sky={}]".format(infile, user_filter)
        chips = getfunc(fname)

        if chips is None:
            v3("Skipping Obsid {} as it does not ".format(obs.obsid) +
               "overlap the requested grid.")
            keep.append(False)
            chipslist.append([])
            skipped_obsids.append(str(obs.obsid))

        else:
            keep.append(True)
            chipslist.append(chips)

    # We could/should allow a single observation through here, but this
    # relies on fixing up some code in merge(). TODO: Is this still true?
    #
    nobs = len(obsinfos)
    nskip = len(skipped_obsids)
    if nskip == nobs:
        raise ValueError("No observations overlap the requested grid: x={}:{} y={}:{}".format(xlo, xhi, ylo, yhi))

    elif nskip == (nobs - 1):
        obsid = [obs.obsid
                 for (flag, obs) in zip(keep, obsinfos) if flag]
        raise ValueError("Only one observation left ({}) that overlaps the requested grid: x={}:{} y={}:{}".format(obsid[0], xlo, xhi, ylo, yhi))

    if nskip != 0:
        if nskip == 1:
            lbl1 = ""
            lbl2 = "it does"
        else:
            lbl1 = "s"
            lbl2 = "they do"

        v1("\nRemoved {} observation{} as {} not overlap the requested grid.".format(nskip, lbl1, lbl2))
        v1("   ObsId{}: {}".format(lbl1, " ".join(skipped_obsids)))

    return (keep, chipslist)


def merge_files(imgfiles, expmap_files, imgfile, expmap, fluxmap,
                lookupTable, toolname, pars, toolversion,
                verbose=1, clobber=False, tmpdir="/tmp/"):
    """Combine the images"""

    run.dmimgcalc_add(imgfiles,
                      imgfile + '[EVENTS_IMAGE]',
                      verbose=verbose,
                      clobber=clobber,
                      lookupTab=lookupTable,
                      tmpdir=tmpdir)

    run.dmimgcalc_add(expmap_files,
                      expmap + '[EXPMAP]',
                      verbose=verbose,
                      clobber=clobber,
                      lookupTab=lookupTable,
                      tmpdir=tmpdir)

    run.fix_bunit(expmap_files[0], expmap, verbose=verbose)

    fi.run_expcorr_image(imgfile, expmap, fluxmap, lookupTable,
                         verbose=verbose, clobber=clobber,
                         tmpdir=tmpdir)

    for filename in [imgfile, expmap, fluxmap]:
        rt.add_tool_history(filename, toolname, pars,
                            toolversion=toolversion)


def shape_to_string(shape):
    """Convert a NumPy shape tuple into a CIAO-friendly string.

    Parameters
    ----------
    shape : tuple of int
        The shape of a NumPy ndarray.

    Returns
    -------
    shapestr : string
        A "readable" version of the shape

    Examples
    --------

    >>> shape_to_string((2, ))
    '2'

    >>> shape_to_string((10, 12))
    '12 x 10'

    """

    shapes = list(shape)
    shapes.reverse()
    return ' x '.join([str(s) for s in shapes])


def adjust_headers(rules, cr, keys, headers):
    """Apply the header merging rules to the headers.

    Parameters
    ----------
    rules : HeaderMerge instance
    cr : pycrates.TABLECrate or pycrates.IMAGECrate instance
    keys : sequence of keywords
        These are all the keys seen in the headers list.
    headers : sequence of dicts
        The headers to merge. Each file is represented as a dict,
        and the items in these are the key,value pairs from the
        file. Every key from the dict is expected to be in the
        keys parameter, but not every key has to appear in all
        dicts.

    """

    for key in keys:
        def getkey(d):
            try:
                return d[key]
            except KeyError:
                return None

        vals = [getkey(d) for d in headers]
        newval = rules.apply(key, vals)
        has_key = cr.key_exists(key)
        if newval is None:
            if has_key:
                cr.delete_key(key)
        else:
            # does this lose comments/units/description if the key already
            # exists?
            pycrates.set_key(cr, key, newval)


# NOTE: exposure_weight and expmap_weight have very-similar structure,
#       so there is currently a lot of repeated code.
#
def exposure_weight(infiles, outfile, lookupTable,
                    clobber=True):
    """Exposure weight the inputs to create an output file.

    Parameters
    ----------
    infiles : list of str
        The files to weight. They must have an EXPOSURE keyword with,
        a positive value, and masked-out pixels set to NaN. They are
        assumed to have any spatial subspace filtered out of them, and
        be on the same grid (and be the same size).
    outfile : str
        The file to create. This is assumed to include any rename of
        the output block if required.
    lookupTable : str
        The name of the lookup table used to merge headers.
    clobber : bool, optional
        Is the output file over-written if it already exists?

    Notes
    -----
    This is performed using Crates - so all the data is read in
    at once rather than done on a pixel-by-pixel basis. This means
    that it is not ideal for "large" files.

    The reason for using Crates over dmimgcalc is the easier
    handling of NaN values.

    The output header is close to what the DataModel merging rules would
    give, but it is not exact. No history items are added for this
    step.

    Only the first block is copied over.

    The behavior of pixels with a value of +infinity or -infinity
    are currently unspecified.
    """

    """
    numerator = ["(img{0}_exposure*img{0})".format(i)
                 for i in range(1, nfiles + 1)]
    denominator = ["img{}_exposure".format(i)
                   for i in range(1, nfiles + 1)]
    combination = "({})/({})".format("+".join(numerator),
                                     "+".join(denominator))
    run.dmimgcalc(infiles=infiles, outfile=outfile,
                  op=combination,
                  lookupTab=lookupTable, tmpdir=tmpdir)
    """

    if len(infiles) == 0:
        raise ValueError("Input files is empty")

    mergerules = HeaderMerge(lookupTable)

    # Calculate
    #     numerator   = sum_i exp_i * pix_i
    #     denominator = sum_i exp_i * mask_i
    #
    # where pix_i has NaN replaced by 0 and mask_i is 1 when origpix_i
    # was finite, otherwise is 0.
    #
    # For now I am not specifying a behavior for pixels set to
    # +infinity / -infinty.
    #
    basecr = None
    numerator = None
    denominator = None

    # Store a dictionary of the header keyword values from each file,
    # and a set of all known keys.
    #
    headers = []
    keys = set()

    for infile in infiles:
        cr = pycrates.read_file(infile)
        if not isinstance(cr, pycrates.IMAGECrate):
            raise ValueError("Not an image: {}".format(infile))

        exp = cr.get_key_value('EXPOSURE')
        if exp is None:
            raise ValueError("No EXPOSURE keyword in {}".format(infile))

        if exp <= 0.0:
            raise ValueError("EXPOSURE keyword = {} in {}".format(exp,
                                                                  infile))

        # NOTE: using NaN as an indicator that the pixel is outside the
        #       filtered data; really should also check the subspace
        #       but this is currently a requirement on the input (that
        #       the subspace and NaN pixels match).
        #
        ivals = cr.get_image().values
        pixvals = exp * np.nan_to_num(ivals)
        expvals = exp * np.isfinite(ivals)

        if numerator is None:
            numerator = pixvals
            denominator = expvals
        else:
            if numerator.shape != pixvals.shape:
                shape = shape_to_string(numerator.shape)
                got = shape_to_string(pixvals.shape)
                raise ValueError("Expected {} but found {} in {}".format(shape, got, infile))

            numerator += pixvals
            denominator += expvals

        # store the header names and values
        #
        names = cr.get_keynames()
        headers.append({k: cr.get_key_value(k) for k in names})
        keys.update(set(names))

        if basecr is None:
            basecr = cr

    # Pixels with no exposure have a value of 0 so will end up as NaN
    # in the output.
    #
    # Note that we force the output to 32 bit rather than 64 bit as
    # there is no need for the extra precision (and mkspfmap creates
    # Real4 images so no point in going more accurate than that).
    #
    res = np.seterr(invalid='ignore')
    try:
        newvals = numerator / denominator
        newvals = newvals.astype(np.float32)
    finally:
        np.seterr(**res)

    basecr.get_image().values = newvals

    # Adjust the header for each key we have seen.
    #
    adjust_headers(mergerules, basecr, keys, headers)

    basecr.write(outfile, clobber=clobber)


def expmap_weight(infiles, expmaps, outfile, lookupTable,
                  clobber=True):
    """Weight the inputs by the exposure maps to create an output file.

    Parameters
    ----------
    infiles : list of str
        The files to weight. They are assumed to have any spatial subspace
        filtered out of them, and be on the same grid (and be the same size).
    expmaps : list of str
        The exposure maps, in the same order as infiles. Pixel values are
        required to be NaN or >= 0. Must match the input files (grid and size).
    outfile : str
        The file to create. This is assumed to include any rename of
        the output block if required.
    lookupTable : str
        The name of the lookup table used to merge headers.
    clobber : bool, optional
        Is the output file over-written if it already exists?

    Notes
    -----
    This is performed using Crates - so all the data is read in
    at once rather than done on a pixel-by-pixel basis. This means
    that it is not ideal for "large" files.

    The reason for using Crates over dmimgcalc is the easier
    handling of NaN values.

    The output header is close to what the DataModel merging rules would
    give, but it is not exact. No history items are added for this
    step.

    Only the first block is copied over.

    The behavior of pixels with a value of +infinity or -infinity
    are currently unspecified.
    """

    """
    dmimgcalc "@psfmap.lis,@expmap.lis" none expweighted_mean.psfmap \
        op="imgout=((img4*img1)+(img5*img2)+(img6*img3))/(img4+img5+img6)" clob+
    """

    if len(infiles) == 0:
        raise ValueError("Input files is empty")

    if len(infiles) != len(expmaps):
        raise ValueError("Input and exposure map lengths do not agree")

    mergerules = HeaderMerge(lookupTable)

    # Calculate
    #     numerator   = sum_i expmap_i * pix_i
    #     denominator = sum_i expmap_i
    #
    # where pix_i and expmap_i have NaN replaced by 0.
    #
    # For now I am not specifying a behavior for pixels set to
    # +infinity / -infinty.
    #
    basecr = None
    numerator = None
    denominator = None

    # Store a dictionary of the header keyword values from each file,
    # and a set of all known keys. This only uses the infiles, and
    # ignores expfiles.
    #
    headers = []
    keys = set()

    for infile, expmap in zip(infiles, expmaps):
        cr = pycrates.read_file(infile)
        if not isinstance(cr, pycrates.IMAGECrate):
            raise ValueError("Not an image: {}".format(infile))

        ecr = pycrates.read_file(expmap)
        if not isinstance(cr, pycrates.IMAGECrate):
            raise ValueError("Not an image: {}".format(expmap))

        # NOTE: using NaN as an indicator that the pixel is outside the
        #       filtered data; really should also check the subspace
        #       but this is currently a requirement on the input (that
        #       the subspace and NaN pixels match).
        #
        evals = ecr.get_image().values
        ivals = cr.get_image().values

        if ivals.shape != evals.shape:
            raise ValueError("Shapes do not match: {} and {}".format(infile, expmap))

        expvals = np.nan_to_num(evals)
        pixvals = expvals * np.nan_to_num(ivals)

        if numerator is None:
            numerator = pixvals
            denominator = expvals
        else:
            if numerator.shape != pixvals.shape:
                shape = shape_to_string(numerator.shape)
                got = shape_to_string(pixvals.shape)
                raise ValueError("Expected {} but found {} in {}".format(shape, got, infile))

            numerator += pixvals
            denominator += expvals

        # store the header names and values
        #
        names = cr.get_keynames()
        headers.append({k: cr.get_key_value(k) for k in names})
        keys.update(set(names))

        if basecr is None:
            basecr = cr

    # Pixels with no exposure have a value of 0 so will end up as NaN
    # in the output.
    #
    # Note that we force the output to 32 bit rather than 64 bit as
    # there is no need for the extra precision (and mkspfmap creates
    # Real4 images so no point in going more accurate than that).
    # It should not be needed here (only in the exptime weight) but
    # left in just to make sure.
    #
    res = np.seterr(invalid='ignore', divide='ignore')
    try:
        newvals = numerator / denominator
        newvals = newvals.astype(np.float32)
    finally:
        np.seterr(**res)

    basecr.get_image().values = newvals

    # Adjust the header for each key we have seen.
    #
    adjust_headers(mergerules, basecr, keys, headers)

    basecr.write(outfile, clobber=clobber)


def merge_psfmaps(mergetype, psfmap, psfmap_files, expmap_files,
                  lookupTable, toolname, pars, toolversion,
                  verbose=1, clobber=False, tmpdir="/tmp/"):
    """Combine the PSF maps.

    It is assumed that the PSF maps have no spatial subspace filters
    (e.g. they were created by fluximage.run_mkpsfmap which explicitly
    removes any spatial filter).
    """

    dmfilttypes = ['min', 'max', 'mean', 'median', 'mid']
    clstr = "yes" if clobber else "no"

    outfile = "{}[PSFMAP]".format(psfmap)
    if mergetype in dmfilttypes:

        run.punlearn("dmimgfilt")
        args = ["infile={}".format(','.join(psfmap_files)),
                "outfile={}".format(outfile),
                "function={}".format(mergetype),
                "mask=point(0,0)",
                "lookupTab={}".format(lookupTable),
                "clobber={}".format(clstr),
                "verbose={}".format(verbose)]
        run.run("dmimgfilt", args)

    elif mergetype == 'exptime':

        exposure_weight(psfmap_files, outfile, lookupTable)

    elif mergetype == 'expmap':

        expmap_weight(psfmap_files, expmap_files, outfile, lookupTable)

    else:
        raise ValueError("Unexpected mergetype={} for combining PSF maps".format(mergetype))

    run.fix_bunit(psfmap_files[0], psfmap, verbose=verbose)

    rt.add_tool_history(psfmap, toolname, pars,
                        toolversion=toolversion)


def merge(process,
          enbands,
          pars,
          outfiles,
          obsinfos,
          toolname,
          toolversion,
          verbose=1,
          psfmerge=None,
          threshold=False,
          clobber=False,
          tmpdir="/tmp/"):
    """Combine the fluximage outputs into single images.
    outfiles is the output of setup_output_names().

    psfmerge must be one of {None, 'exptime', 'expmap', 'min', 'max'}.
    It is required that if PSF maps be created, psfmerge not be None,
    and if they are not created psfmerge is None. This is not checked
    for here.
    """

    nobs = sum(process)
    ebands = [enband.bandlabel for enband in enbands]

    # We need to filter the images/expmaps/image_thresh values in outfiles
    # by the process flag.
    #
    def extract_fileinfo(finfo):
        out = {}
        for (key, files) in finfo.items():
            out[key] = [fname
                        for (flag, fname) in zip(process, files) if flag]

        return out

    if threshold:
        images = extract_fileinfo(outfiles['image_thresh'])
        expmaps = extract_fileinfo(outfiles['expmap_thresh'])
    else:
        images = extract_fileinfo(outfiles['images'])
        expmaps = extract_fileinfo(outfiles['expmaps'])

    # In other scripts the verbose level for the tools is one less than the
    # script verbosity; so apply that here.
    verbose -= 1
    if verbose < 0:
        verbose = 0
    elif verbose == 4:
        verbose = 5

    ltable = run.get_lookup_table('obsidmerge', pathfrom=__file__)

    v3("Modifying lookup table: {}".format(ltable))
    newtab = create_lookup_table(ltable, obsinfos,
                                 tmpdir=tmpdir)
    ltable = newtab.name

    # We could do this in parallel, but may not be a good idea if the
    # data sets are large, so leave as is for now.
    #
    v1("\nCombining {} observations.".format(nobs))
    if threshold:
        obsid_images = outfiles['out_thresh_images']
        obsid_expmaps = outfiles['out_thresh_expmaps']
    else:
        obsid_images = outfiles['out_images']
        obsid_expmaps = outfiles['out_expmaps']

    for (eband, imgfile, expmap, fluxmap) in \
            zip(ebands, obsid_images, obsid_expmaps,
                outfiles['out_fluxmaps']):

        merge_files(images[eband], expmaps[eband],
                    imgfile, expmap, fluxmap,
                    ltable, toolname, pars, toolversion,
                    verbose=verbose, clobber=clobber, tmpdir=tmpdir)

    if psfmerge is not None:
        psfmaps = outfiles['psfmaps']
        for (eband, psfmap) in zip(ebands, outfiles['out_psfmaps']):

            merge_psfmaps(psfmerge, psfmap, psfmaps[eband], expmaps[eband],
                          ltable, toolname, pars, toolversion,
                          verbose=verbose, clobber=clobber, tmpdir=tmpdir)

    try:
        rt.add_tool_history(outfiles['mergedevtfile'], toolname, pars,
                            toolversion=toolversion)
    except KeyError:
        pass

    # Let the user know what was created
    #
    if len(ebands) > 1:
        lbl = 's are:'
    else:
        lbl = ' is:'

    spacer = '     '

    def display(typestr, filenames):
        v1("{}{}".format(typestr, lbl))
        fnames = ('\n' + spacer).join(filenames)
        v1("{}{}\n".format(spacer, fnames))

    v1("\nThe following files were created:\n")
    if threshold:
        display("The co-added clipped counts image",
                outfiles['out_thresh_images'])
        display("The co-added clipped exposure map",
                outfiles['out_thresh_expmaps'])
    else:
        display("The co-added counts image", outfiles['out_images'])
        display("The co-added exposure map", outfiles['out_expmaps'])

    if psfmerge is not None:
        display("The combined PSF map", outfiles['out_psfmaps'])

    display("The co-added exposure-corrected image", outfiles['out_fluxmaps'])


def validate_obsinfo_params(obsinfos,
                            asolfiles,
                            badpixfiles,
                            maskfiles,
                            dtffiles=None,
                            tangent=True,
                            tol=1.4e-5):
    """Ensure the parameter values are sensible - e.g. file exists
    and that ancillary files can be found if set.

    If tangent is True then the observations are checked to make sure
    that the tangent points are the same. If they are not within tol
    degrees (the default of 1.4e-5 is 0.05 arcsec), a warning is
    displayed (but the files are still changed).

    In CIAO 4.6 the pbkfiles parameter was removed.
    """

    if tangent:
        # Warn if the tangent points of the files do not match,
        # but do not reject the files (at least for now). This
        # comparison is based on the CIAO 4.6 dmmerge header rules
        # tolerance, namely:
        #
        # % grep NOM ${ASCDS_CALIB}/dmmerge_header_lookup.txt
        # RA_NOM     WarnOmit-0.0003
        # DEC_NOM    WarnOmit-0.0003
        # ROLL_NOM   WarnOmit-1.0
        #
        # but the tolerance of 0.0003 degrees is applied to the
        # separation between the two points. Now, 3e-4 degrees
        # is 1.08 arcsec which seems a bit large, so change
        # this to 3e-5 degrees, ie 0.11 arcsec. And then
        # decrease to 1.4e-5 degrees, which is 0.0504 arcsec.
        #
        (ra0, dec0) = obsinfos[0].tangentpoint
        for obs in obsinfos[1:]:
            (rai, deci) = obs.tangentpoint
            sepdeg = coords.utils.point_separation(ra0, dec0, rai, deci)
            separcmin = sepdeg * 3600.0
            v2("Separation in tangent-point of {} from {} is {} arcsec".format(obs.obsid,
                                                                               obsinfos[0].obsid,
                                                                               separcmin))

            if sepdeg > tol:
                # .2f requires that the tolerance is not significantly smaller
                # than 0.1 arcsec.
                v1("WARNING: Tangent points differ by {:.2f} arcsec: {} vs {}".format(
                    separcmin,
                    obs.get_evtfile(),
                    obsinfos[0].get_evtfile()))
                v2("(ra,dec) = {},{} vs {},{}".format(ra0, dec0, rai, deci))

    # Set up ancillary files
    #
    setup_obsid_asol(obsinfos, asolfiles)
    setup_obsid_bpix(obsinfos, badpixfiles)
    setup_obsid_mask(obsinfos, maskfiles)
    if obsinfos[0].instrument == 'HRC':
        setup_obsid_dtf(obsinfos, dtffiles)


def handle_xygrid(pfile, instrument, pars, params):
    """Calculate image size/binning. At present it is a bit confusing since there
    are multiple parameters: xygrid, maxsize, and binsize.

    If maxsize is given then we force binsize to 1.

    binsize defaults to INDEF which is 8 for ACIS, 32 for HRC.

    Both the pars and params dictionaries are changed by this routine.
    """

    pars['xygrid'] = paramio.pgetstr(pfile, 'xygrid')
    xygrid = pars['xygrid'].strip()
    if xygrid == "":
        pars['maxsize'] = paramio.pgetstr(pfile, 'maxsize')
        if pars['maxsize'] == 'INDEF':
            params['maxsize'] = None

            pars['binsize'] = paramio.pgetstr(pfile, 'binsize')
            if pars['binsize'] == 'INDEF':
                if instrument == 'ACIS':
                    params['bin'] = 8
                elif instrument == 'HRC':
                    params['bin'] = 32
                else:
                    raise ValueError("Internal error: unknown INSTRUME={}".format(instrument))

            else:
                params['bin'] = paramio.pgetd(pfile, 'binsize')
                if params['bin'] <= 0:
                    raise ValueError("binsize={} is not valid, it must be a number greater than zero.".format(params['bin']))

        else:
            params['maxsize'] = paramio.pgeti(pfile, 'maxsize')
            # override the binning/is this going to break something?
            # possibly, because use bin to get the x/y range, but then do
            # we need to re-generate this when the actual binning is known ?
            params['bin'] = 1

    else:
        (xygrid, binsize, xrng, yrng, sizes) = utils.parse_xygrid(xygrid)
        pars['maxsize'] = 'INDEF'
        pars['binsize'] = 'INDEF'
        params['maxsize'] = None
        params['bin'] = binsize
        params['xrange'] = xrng
        params['yrange'] = yrng
        params['sizes'] = sizes

    params['xygrid'] = xygrid

# End
