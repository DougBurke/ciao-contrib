"""Basic tests of the runtool interface"""

import os
from pathlib import Path

import pytest

import ciao_contrib.runtool as rt
from ciao_contrib.logger_wrapper import initialize_logger, set_verbosity


ALL_TOOLS = rt.list_tools()
SPECIAL_TOOLS = ['axbary', 'dmgti', 'evalpos', 'fullgarf',
                 'mean_energy_map', 'pileup_map', 'tgdetect',
                 'wavdetect']
PAR_TOOLS = ['ardlib', 'colors', 'dax', 'geom', 'imagej_lut', 'lut', 'ximage_lut']

STANDARD_TOOLS = list(set(ALL_TOOLS) - set(SPECIAL_TOOLS) - set(PAR_TOOLS))


# The current tests assume a conda-installed CIAO environment
#
ASCDS_INSTALL = Path(os.getenv('ASCDS_INSTALL'))


initialize_logger('test_runtool')
set_verbosity(0)


@pytest.fixture
def verbose5():

    set_verbosity(5)
    yield
    set_verbosity(0)


def test_have_ascds_install():
    """Needed for other tests"""

    assert ASCDS_INSTALL.is_dir()


def test_expected_tools():
    assert len(ALL_TOOLS) == 199
    assert len(STANDARD_TOOLS) == 184


@pytest.mark.parametrize("expected", STANDARD_TOOLS)
def test_expected_standard(expected):
    tool1 = getattr(rt, expected)
    assert isinstance(tool1, rt.CIAOToolParFile)

    tool2 = rt.make_tool(expected)
    assert isinstance(tool2, rt.CIAOToolParFile)

    assert tool1 != tool2
    assert str(tool1) == str(tool2)

    out = f'<CIAO tool: {expected}>'
    assert repr(tool1) == out
    assert repr(tool2) == repr(tool1)


@pytest.mark.parametrize("expected", SPECIAL_TOOLS)
def test_expected_special(expected):
    tool1 = getattr(rt, expected)
    assert isinstance(tool1, rt.CIAOToolDirect)

    tool2 = rt.make_tool(expected)
    assert isinstance(tool2, rt.CIAOToolDirect)

    assert tool1 != tool2
    assert str(tool1) == str(tool2)

    out = f'<CIAO tool: {expected}>'
    assert repr(tool1) == out
    assert repr(tool2) == repr(tool1)


@pytest.mark.parametrize("expected", PAR_TOOLS)
def test_expected_par(expected):
    tool1 = getattr(rt, expected)
    assert isinstance(tool1, rt.CIAOParameter)

    tool2 = rt.make_tool(expected)
    assert isinstance(tool2, rt.CIAOParameter)

    assert tool1 != tool2
    assert str(tool1) == str(tool2)

    out = f'<CIAO parameter file: {expected}>'
    assert repr(tool1) == out
    assert repr(tool2) == repr(tool1)


def test_error_on_invalid_attribute():
    with pytest.raises(AttributeError) as ae1:
        rt.dmstat.foo = 1

    emsg = "There is no parameter for dmstat that matches 'foo'"
    assert str(ae1.value) == emsg

    tool = rt.make_tool('dmstat')
    with pytest.raises(AttributeError) as ae2:
        tool.foo = 1

    assert str(ae2.value) == emsg


def test_error_on_int_parameter_too_low():
    with pytest.raises(ValueError) as ve1:
        rt.dmstat.maxiter = 0

    emsg = "dmstat.maxiter must be >= 1 but set to 0"
    assert str(ve1.value) == emsg

    tool = rt.make_tool('dmstat')
    with pytest.raises(ValueError) as ve2:
        tool.maxiter = 0

    assert str(ve2.value) == emsg


def test_error_on_int_parameter_too_high():
    with pytest.raises(ValueError) as ve1:
        rt.dmstat.verbose = 6

    emsg = "dmstat.verbose must be <= 5 but set to 6"
    assert str(ve1.value) == emsg

    tool = rt.make_tool('dmstat')
    with pytest.raises(ValueError) as ve2:
        tool.verbose = 6

    assert str(ve2.value) == emsg


def test_error_on_real_parameter_too_low():
    with pytest.raises(ValueError) as ve1:
        rt.vtpdetect.mincutoff = -1

    emsg = "vtpdetect.mincutoff must be >= 0 but set to -1"
    assert str(ve1.value) == emsg

    tool = rt.make_tool('vtpdetect')
    with pytest.raises(ValueError) as ve2:
        tool.mincutoff = -1

    assert str(ve2.value) == emsg


def test_error_on_real_parameter_too_high():
    with pytest.raises(ValueError) as ve1:
        rt.vtpdetect.mincutoff = 30

    emsg = "vtpdetect.mincutoff must be <= 10 but set to 30"
    assert str(ve1.value) == emsg

    tool = rt.make_tool('vtpdetect')
    with pytest.raises(ValueError) as ve2:
        tool.mincutoff = 30

    assert str(ve2.value) == emsg


def test_parameter_check_is_case_sensitive():

    with pytest.raises(AttributeError) as ae1:
        rt.dmstat.CENTROID

    emsg = "There is no parameter for dmstat that matches 'CENTROID'"

    assert str(ae1.value) == emsg

    with pytest.raises(AttributeError) as ae2:
        rt.make_tool('dmstat').CENTROID

    assert str(ae2.value) == emsg


@pytest.mark.parametrize("requested,expected",
                         [("centroi", "centroid"),
                          ("cent", "centroid"),
                          ("cen", "centroid"),
                          ("ce", "centroid"),
                          ("med", "median"),
                          ("inf", "infile")])
def test_dmstat_parameter_match(requested, expected):
    """Check we can use unique name subsets"""

    a1 = getattr(rt.dmstat, requested)
    a2 = getattr(rt.make_tool('dmstat'), requested)

    b = getattr(rt.dmstat, expected)
    if b is None:
        assert a1 is None
        assert a2 is None
    else:
        assert a1 == b
        assert a2 == b


def test_dmstat_parameter_match_not_unique():

    with pytest.raises(AttributeError) as ae1:
        rt.dmstat.c

    emsg = "Multiple matches for dmstat parameter 'c', choose from:\n" + \
        "  centroid clip"

    assert str(ae1.value) == emsg

    with pytest.raises(AttributeError) as ae2:
        rt.make_tool('dmstat').c

    assert str(ae2.value) == emsg


@pytest.mark.parametrize('val', [True, 1, "1", "yes", "YES", "true", "on"])
def test_set_boolean_true(val):
    tool = rt.make_tool('dmstat')
    assert not tool.median

    tool.median = val
    assert tool.median


@pytest.mark.parametrize('val', [False, 0, "0", "no", "No", "false", "off"])
def test_set_boolean_false(val):
    tool = rt.make_tool('dmstat')
    assert tool.sigma

    tool.sigma = val
    assert not tool.sigma


@pytest.mark.parametrize('val', ["truthy", "falsey", "ya", ""])
def test_set_boolean_invalid(val):
    tool = rt.make_tool('dmstat')
    with pytest.raises(ValueError) as ve:
        tool.sigma = val

    assert str(ve.value) == f"The dmstat.sigma value should be a boolean, not '{val}'"


def test_reset_params():
    """We can set and reset values"""

    tool = rt.make_tool('dmstat')
    orig = str(tool)

    def check():
        assert tool.infile is None
        assert tool.centroid
        assert tool.nsigma == pytest.approx(3)
        assert tool.maxiter == 20
        assert tool.out_mean is None

    check()

    infile = 'foo/bar/bax[energy=2:3, sky=region(bob.reg)][bin sky=::4]'
    tool.infile = infile
    tool.centroid = False
    tool.nsigma = 2.5
    tool.maxiter = 2

    assert tool.infile == infile
    assert not tool.centroid
    assert tool.nsigma == pytest.approx(2.5)
    assert tool.maxiter == 2
    assert tool.out_mean is None

    text = str(tool)
    assert text != orig

    lines = text.split('\n')
    assert len(lines) == 28
    assert lines[0] == 'Parameters for dmstat:'
    assert lines[1] == ''
    assert lines[2] == 'Required parameters:'
    assert lines[3] == f'              infile = {infile}  Input file specification'
    assert lines[4] == ''
    assert lines[5] == 'Optional parameters:'
    assert lines[6] == '            centroid = False            Calculate centroid if image?'

    assert lines[10] == '              nsigma = 2.5              Number of sigma to clip'
    assert lines[11] == '             maxiter = 2                Maximum number of iterations'

    assert lines[18] == '            out_mean =                  Output Mean Value'

    tool.punlearn()
    assert str(tool) == orig
    check()


@pytest.mark.parametrize("toolname", STANDARD_TOOLS)
def test_write_parfile_standard(toolname, tmp_path):

    if toolname in ['dmimg2jpg', 'mkgrmf', 'mkgarf']:
        # mkgrmf and mkgarf fail because grating_arm is set to '' but this
        # is not a valid enumeration for them.
        #
        # dmimg2jpg fails presumably because lutfile defaults
        # to ')lut.grey' and we don't support this level of redirect/
        #
        pytest.skip(f'We know writing out {toolname} fails due to reasons')

    parfile = tmp_path / f'standard.{toolname}.par'

    tool = rt.make_tool(toolname)
    assert not parfile.exists()
    tool.write_params(str(parfile))
    assert parfile.exists()

    cts = parfile.read_text()

    # why are these three special? Probably MIT heritege/
    #
    if toolname in ['mkarf', 'mkexpmap', 'mkinstmap']:
        assert 'mode,s,h,"hl",ql|hl|q|h,,' in cts
    else:
        assert 'mode,s,h,"hl",,,' in cts

    # It would be nice to compare to the "default" values
    # but the conversion isn't perfect, so the following has
    # many failures I don't want to address right now.
    #
    orig = ASCDS_INSTALL / 'param' / f'{toolname}.par'
    assert orig.is_file()

    cts2 = open(orig, 'rt').read()

    assert ('mode,s,h,"ql",,,' in cts2) or \
        ('mode,s,h,ql,,,' in cts2) or \
        ('mode,s,h,ql' in cts2) or \
        ('mode,s,h,"h",,,' in cts2) or \
        ('mode,s,h,"ql",ql|hl|q|h,,' in cts2)

    cts = [l for l in cts.split('\n') if not l.startswith('mode,')]
    cts2 = [l for l in cts2.split('\n') if not l.startswith('mode,')]

    wrong = []
    for a, b in zip(cts, cts2):
        if a.strip() == b.strip():
            continue

        print(toolname)
        print(a.strip())
        print(b.strip())
        print("---")
        wrong.append((a, b))

    # This is ugly - it would be nice to check the actual differences
    # but that's a lot of work
    #
    nwrong = len(wrong)
    nwrongs = {'acis_find_afterglow': 2,
               'acis_process_events': 1,
               'acis_streak_map': 2,
               'acisreadcorr': 4,
               'aplimits': 3,
               'aprates': 15,
               'asphist': 2,
               'arestore': 2,
               'arfcorr': 4,
               'bkg_fixed_counts': 1,
               'celldetect': 1,
               'centroid_map': 1,
               'combine_grating_spectra': 2,
               'combine_spectra': 1,
               'correct_periscope_drift': 3,
               'destreak': 2,
               'dmcoords': 14,
               'dmellipse': 2,
               'dmextract': 1,
               'dmmakepar': 3,
               'dmhistory': 1,
               'dmimgadapt': 2,
               'dmimgblob': 1,
               'dmimglasso': 6,
               'dmimgpick': 1,
               'dmimgthresh': 1,
               'dmkeypar': 2,
               'dmradar': 1,
               'dmreadpar': 3,
               'dmregrid': 1,
               'dmregrid2': 5,
               'dmtcalc': 1,
               'download_obsid_caldb': 3,
               'ecf_calc': 1,
               'eff2evt': 1,
               'fine_astro': 1,
               'find_chandra_obsid': 5,
               'find_mono_energy': 1,
               'get_dither_parameters': 4,
               'get_src_region': 3,
               'glvary': 1,
               'hrc_build_badpix': 4,
               'hrc_process_events': 8,
               'imgmoment': 15,
               'make_psf_asymmetry_region': 3,
               'mkacisrmf': 4,
               'mkarf': 2,
               'merge_too_small': 2,
               'mkpsfmap': 3,
               'mkregmap': 1,
               'mkrmf': 1,
               'mkrprm': 3,
               'modelflux': 1,
               'monitor_photom': 1,
               'mtl_build_gti': 1,
               'obsid_search_csc': 3,
               'pathfinder': 1,
               'pfold': 1,
               'psf_contour': 2,
               'psf_project_ray': 2,
               'psfsize_srcs': 1,
               'rank_roi': 1,
               'reproject_image': 2,
               'reproject_image_grid': 6,
               'roi': 1,
               'search_csc': 3,
               'simulate_psf': 7,
               'tg_create_mask': 40,
               'tg_resolve_events': 5,
               'tgidselectsrc': 1,
               'wrecon': 1,
               'wtransform': 1,
               }

    try:
        assert nwrong == nwrongs[toolname], (toolname, nwrong)
    except KeyError:
        assert nwrong == 0, (toolname, nwrong)


@pytest.mark.parametrize("toolname", SPECIAL_TOOLS)
def test_write_parfile_special(toolname, tmp_path):

    parfile = tmp_path / f'special.{toolname}.par'

    tool = rt.make_tool(toolname)
    assert not parfile.exists()
    tool.write_params(str(parfile))
    assert parfile.exists()

    cts = parfile.read_text()

    assert 'mode,s,h,"hl",,,' in cts

    # It would be nice to compare to the "default" values
    # but the conversion isn't perfect, so the following has
    # many failures I don't want to address right now.
    #
    orig = ASCDS_INSTALL / 'param' / f'{toolname}.par'
    assert orig.is_file()

    cts2 = open(orig, 'rt').read()

    assert ('mode,s,h,"ql",,,' in cts2) or \
        ('mode,s,h,ql' in cts2)

    cts = [l for l in cts.split('\n') if not l.startswith('mode,')]
    cts2 = [l for l in cts2.split('\n') if not l.startswith('mode,')]

    wrong = []
    for a, b in zip(cts, cts2):
        if a.strip() == b.strip():
            continue

        print(a.strip())
        print(b.strip())
        wrong.append((a, b))

    # This is ugly - it would be nice to check the actual differences
    # but that's a lot of work
    #
    nwrong = len(wrong)
    if toolname == 'dmgti':
        assert nwrong == 1
    elif toolname == 'evalpos':
        assert nwrong == 1
    elif toolname == 'mean_energy_map':
        assert nwrong == 1
    elif toolname == 'tgdetect':
        assert nwrong == 4
    elif toolname == 'wavdetect':
        assert nwrong == 2
    else:
        assert nwrong == 0


@pytest.mark.parametrize("toolname", PAR_TOOLS)
def test_write_parfile_par(toolname, tmp_path):

    parfile = tmp_path / f'par.{toolname}.par'

    tool = rt.make_tool(toolname)
    assert not parfile.exists()
    tool.write_params(str(parfile))
    assert parfile.exists()

    cts = parfile.read_text()

    assert ('mode,s,h,"hl",,,' in cts) or \
        ('mode,s,h,"hl",ql|hl|q|h,,' in cts)

    # It would be nice to compare to the "default" values
    # but the conversion isn't perfect, so the following has
    # many failures I don't want to address right now.
    #
    orig = ASCDS_INSTALL / 'param' / f'{toolname}.par'
    assert orig.is_file()

    cts2 = open(orig, 'rt').read()

    print([l for l in cts2.split('\n') if l.startswith('mode')])

    if toolname in ['ardlib', 'dax', 'geom']:
        assert ('mode,s,h,"ql",,,' in cts2) or \
            ('mode,s,h,"h",,,' in cts2) or \
            ('mode,s,h,h,,,' in cts2) or \
            ('mode,s,h,"hl","ql|hl|q|h",,' in cts2)
    else:
        assert '\nmode,' not in cts2

    cts = [l for l in cts.split('\n') if not l.startswith('mode,')]
    cts2 = [l for l in cts2.split('\n') if not l.startswith('mode,')]

    wrong = []
    for a, b in zip(cts, cts2):
        if a.strip() == b.strip():
            continue

        print(a.strip())
        print(b.strip())
        wrong.append((a, b))

    # This is ugly - it would be nice to check the actual differences
    # but that's a lot of work
    #
    nwrong = len(wrong)
    if toolname == 'dmgti':
        assert nwrong == 1
    elif toolname == 'evalpos':
        assert nwrong == 1
    elif toolname == 'mean_energy_map':
        assert nwrong == 1
    elif toolname == 'tgdetect':
        assert nwrong == 4
    elif toolname == 'wavdetect':
        assert nwrong == 2
    else:
        assert nwrong == 0


@pytest.mark.parametrize("filename", [None, 'dmcopy.par'])
def test_write_params_same_directory(filename, tmp_path, verbose5):
    """Check issue #448"""

    # Technically we cuold run when pfiles is None
    pfiles = rt.get_pfiles(userdir=True)
    assert pfiles is not None
    assert len(pfiles) == 1

    os.chdir(tmp_path)

    # The parameter file is written to the userdir
    #
    outfile = Path(pfiles[0]) / 'dmcopy.par'

    # We can not depend on the file not existing
    # assert not outfile.exists()

    tool = rt.make_tool('dmcopy')
    tool.infile = '../foo/bar.fits[foo=23:][cols bob]'
    tool.verbose = 2
    tool.clobber = True
    tool.write_params(filename)

    assert outfile.exists()

    cts = outfile.read_text()
    lines = cts.split('\n')
    assert len(lines) == 8
    assert lines[0] == 'infile,f,a,"../foo/bar.fits[foo=23:][cols bob]",,,"Input dataset/block specification"'
    assert lines[1] == 'outfile,f,a,"",,,"Output dataset name"'
    assert lines[2] == 'kernel,s,h,"default",,,"Output file format type"'
    assert lines[3] == 'option,s,h,"",,,"Option - force output type"'
    assert lines[4] == 'verbose,i,h,2,0,5,"Debug Level"'
    assert lines[5] == 'clobber,b,h,yes,,,"Clobber existing file"'
    assert lines[6] == 'mode,s,h,"hl",,,'
    assert lines[7] == ''


def test_write_params_same_directory_renamed(tmp_path, verbose5):
    """Check issue #448"""

    os.chdir(tmp_path)
    outfile = tmp_path / 'other.par'

    assert not outfile.exists()

    tool = rt.make_tool('dmcopy')
    tool.infile = '../foo/bar.fits[foo=23:][cols bob]'
    tool.verbose = 2
    tool.clobber = True
    tool.write_params('other.par')

    assert outfile.exists()

    cts = outfile.read_text()
    lines = cts.split('\n')
    assert len(lines) == 8
    assert lines[0] == 'infile,f,a,"../foo/bar.fits[foo=23:][cols bob]",,,"Input dataset/block specification"'
    assert lines[1] == 'outfile,f,a,"",,,"Output dataset name"'
    assert lines[2] == 'kernel,s,h,"default",,,"Output file format type"'
    assert lines[3] == 'option,s,h,"",,,"Option - force output type"'
    assert lines[4] == 'verbose,i,h,2,0,5,"Debug Level"'
    assert lines[5] == 'clobber,b,h,yes,,,"Clobber existing file"'
    assert lines[6] == 'mode,s,h,"hl",,,'
    assert lines[7] == ''


#@pytest.mark.parametrize("filename", [None, 'other.par', pytest.param('dmcopy.par', marks=pytest.mark.xfail)])
@pytest.mark.parametrize("filename", [None, 'other.par', 'dmcopy.par'])
def test_write_params_same_directory_pfiles(filename, tmp_path, verbose5):
    """Check issue #448"""

    dname = tmp_path / 'temp'
    with rt.new_pfiles_environment(dirname=dname, ardlib=False, copyuser=False):

        # This should have been created via new_pfiles_environment
        os.chdir(dname)

        # The parameter file is written to the userdir
        #
        if filename is None:
            outfile = dname / 'dmcopy.par'
        else:
            outfile = dname / filename

        # We can not depend on the file not existing
        # assert not outfile.exists()

        tool = rt.make_tool('dmcopy')
        tool.infile = '../foo/bar.fits[foo=23:][cols bob]'
        tool.verbose = 2
        tool.clobber = True
        tool.write_params(filename)

        assert outfile.exists()
        cts = outfile.read_text()

    lines = cts.split('\n')
    assert len(lines) == 8
    assert lines[0] == 'infile,f,a,"../foo/bar.fits[foo=23:][cols bob]",,,"Input dataset/block specification"'
    assert lines[1] == 'outfile,f,a,"",,,"Output dataset name"'
    assert lines[2] == 'kernel,s,h,"default",,,"Output file format type"'
    assert lines[3] == 'option,s,h,"",,,"Option - force output type"'
    assert lines[4] == 'verbose,i,h,2,0,5,"Debug Level"'
    assert lines[5] == 'clobber,b,h,yes,,,"Clobber existing file"'
    assert lines[6] == 'mode,s,h,"hl",,,'
    assert lines[7] == ''


@pytest.mark.parametrize("val,ptype",
                         [(True, "bool"),
                          (1, "int"),
                          ("True", "str"),
                          ("1", "str"),
                          ("yes", "str")])
def test_verbosity_set_boolean(val, ptype, verbose5, caplog):
    """Check we get the expected messages when setting a boolean"""

    tool = rt.make_tool('dmimg2jpg')
    assert not tool.invert

    tool.invert = val
    assert tool.invert

    # All messages are verbose=5
    #
    assert len(caplog.records) == 5
    for lname, lvl, _ in caplog.record_tuples:
        assert lname == 'cxc.ciao.contrib.module.runtool'
        assert lvl == 10

    def check(i, msg):
        assert caplog.record_tuples[i][2] == msg

    check(0, 'Calling punlearn on tool dmimg2jpg')
    check(1, f"Entering _validate for name=invert val={val} (type=<class '{ptype}'>) store=True")
    check(2, f'Validating dmimg2jpg.invert val={val} as ...')
    check(3, '... a boolean')
    check(4, "Setting dmimg2jpg.invert to True (<class 'bool'>)")


@pytest.mark.parametrize("val,ptype",
                         [(5, "int"),
                          ("5", "str")])
def test_verbosity_set_int(val, ptype, verbose5, caplog):
    """Check we get the expected messages when setting an integer"""

    tool = rt.make_tool('dmimg2jpg')
    assert tool.colorshift == 0

    tool.colorshift = val
    assert tool.colorshift == 5

    # All messages are verbose=5
    #
    assert len(caplog.records) == 5
    for lname, lvl, _ in caplog.record_tuples:
        assert lname == 'cxc.ciao.contrib.module.runtool'
        assert lvl == 10

    def check(i, msg):
        assert caplog.record_tuples[i][2] == msg

    check(0, 'Calling punlearn on tool dmimg2jpg')
    check(1, f"Entering _validate for name=colorshift val={val} (type=<class '{ptype}'>) store=True")
    check(2, f'Validating dmimg2jpg.colorshift val={val} as ...')
    check(3, '... an integer')
    check(4, "Setting dmimg2jpg.colorshift to 5 (<class 'int'>)")


def test_verbosity_set_str(verbose5, caplog):
    """Check we get the expected messages when setting a string"""

    tool = rt.make_tool('dmimg2jpg')
    assert tool.infile is None

    infile = "foo.fits[sky region(/a/b/c.reg)]"
    tool.infile = infile
    assert tool.infile == infile

    # All messages are verbose=5
    #
    assert len(caplog.records) == 5
    for lname, lvl, _ in caplog.record_tuples:
        assert lname == 'cxc.ciao.contrib.module.runtool'
        assert lvl == 10

    def check(i, msg):
        assert caplog.record_tuples[i][2] == msg

    check(0, 'Calling punlearn on tool dmimg2jpg')
    check(1, f"Entering _validate for name=infile val={infile} (type=<class 'str'>) store=True")
    check(2, f'Validating dmimg2jpg.infile val={infile} as ...')
    check(3, '... something else')
    check(4, f"Setting dmimg2jpg.infile to {infile} (<class 'str'>)")
