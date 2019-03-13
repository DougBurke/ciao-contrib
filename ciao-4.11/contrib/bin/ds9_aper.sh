#! /bin/bash
# 
#  Copyright (C) 2012-2019  Smithsonian Astrophysical Observatory
#
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 3 of the License, or
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



ds9=$1

bands="$2"
mdl="$3"
mdlp="$4"
amdl="$5"
amdlp="$6"
psfmethod="$7"

nxpa=`xpaaccess -n ${ds9}`
if test $nxpa -ne 1
then
  echo "# -------------------"
  echo "Multiple (${nxpa}) ds9's are running using the same title: '${ds9}'.  Please close the other windows and restart."
  exit 1
fi




src=`xpaget ${ds9} regions -format ciao source -strip yes selected | tr ";" "+" | sed 's,\+$,,;s,\+\-,\-,g' `
bkg=`xpaget ${ds9} regions -format ciao background -strip yes selected | tr ";" "+" | sed 's,\+$,,;s,\+\-,\-,g'` 


fmt=`xpaget ${ds9} fits type`

if test x$fmt = xtable
then
  :
else
  echo "#-------"
  echo "Must be using an event file"
  exit 1
fi

if test x$src = x
then
  echo "#-------"
  echo "No source region found"
  exit 1
fi

nsrc=`echo "${src}" | grep "^-" `
if test x"${src}" = x"${nsrc}"
then
  echo "#--------"
  echo "Source region cannot begin with an excluded shape: ${src}"
  exit 1
fi

if test x$bkg = x
then
  echo "#-------"
  echo "No background region found"
  exit 1
fi


nbkg=`echo "${bkg}" | grep "^-"`
if test x"${bkg}" = x"${nbkg}"
then
  echo "#--------"
  echo "Background region cannot begin with an excluded shape: ${bkg}"
  exit 1
fi


# ds9 filters should not be used, remove them.
file=`xpaget ${ds9} file | sed 's,\[.*,,'`

rdir=$DAX_OUTDIR/aper/$$/
root=${rdir}/out
mkdir -p $rdir


dmcopy "${file}[(x,y)=${src}]" - | dmstat "-[cols ra,dec]"  verb=0
ra=`stk_read_num ")dmstat.out_mean" 1 e+ `
dec=`stk_read_num ")dmstat.out_mean" 2 e+ `

echo "#-------------"
srcflux infile="${file}" \
  band="${bands}" \
  model="${mdl}"\
  paramvals="${mdlp}" \
  absmodel="${amdl}" \
  absparams="${amdlp}" \
  pos="${ra},${dec}" \
  outroot="${root}" \
  bkgresp=no \
  srcreg="${src}" \
  bkgreg="${bkg}" \
  psfmethod="${psfmethod}" \
  clobber=yes \
  tmpdir=${rdir} 2>&1

if test $? -ne 0
then
  if test x$rdir != x
  then  
    /bin/rm ${rdir}/*
  fi
  echo "Error running srcflux command"
  exit 1
fi


echo ""
echo "Output files are located in $rdir"
exit 0
