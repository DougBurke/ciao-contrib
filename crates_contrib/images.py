#
#  Copyright (C) 2012, 2015, 2016, 2019
#            Smithsonian Astrophysical Observatory
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
Image-specific Crates routines.

At present there is only one routine - imextent.

"""

from pytransform import LINEAR2DTransform

__all__ = ('imextent', )


def imextent(img, xmin, xmax, ymin, ymax, limits='center'):
    """Create a linear transform for the image axes.

    Returns a 2D linear transform object that represents the
    mapping from "pixel" units (e.g. logical values) to
    a linearly scaled system (offset and scale change, no
    rotation). One use of this is to mimic the extent
    argument from matplotlib's imshow command, as discussed
    in the examples below.

    Parameters
    ----------
    img : 2D NumPy array
    xmin, xmax, ymin, ymax : float
        The coordinates of the lower-left and upper-right
        corners of the image in the transformed (non-logical)
        system.
    limits : {'center', 'edge'}
        Do the coordinates (xmin, ..., ymax) refer to the
        center of the pixels, or their edges. In FITS convention,
        the bottom-left pixel is centered on 1,1 and the top-right
        pixel is nx,ny (for a nx by ny grid). With limits='center'
        xmin,xmax refers to the center of the lower-left pixel
        (i.e. 1,1 in FITS terminology) whereas with limits='edge'
        it refers to the bottom-left corner (0.5,0.5 in FITS).

    Returns
    -------
    tr : pytransform.LINEAR2DTransform
        The transform object containing the coordinate mapping.

    Notes
    -----
    The logical coordinate system follows the FITS standard, so the
    first pixel is (1,1) and not (0,0), and the X axis values are
    given first.

    Examples
    --------

    The following example creates a 40 pixel wide by 20 pixel high
    image, zi, where the X axis goes from 40 to 60 and the Y
    axis 10 to 20. The imextent call creates a transform object.

    >>> yi, xi = np.mgrid[10:20:20j, 40:60:40j]
    >>> zi = 100.0 / np.sqrt((xi - 45.62) ** 2 + (yi - 14.7) ** 2)
    >>> tr = imextent(zi, 40, 60, 10, 20)

    The transform object can be used to convert between logical
    coordinates (where 1,1 refers to the center of the lower-left
    pixel) and the data coordinates:

    >>> print(tr.apply([[1,1], [40,20]]))
    [[40 10]
     [60 20]]

    and the invert method goes from data to logical coordinates:

    >>> print(tr.invert([[45.0, 15.0]]))
    [[ 10.75  10.5 ]]

    The following examples use a 4 pixel by 3 pixel image:

    >>> img = np.arange(0, 12).reshape(3, 4)

    The default value for the limits argument is 'center', which
    means that the given coordinates - in this case 10,-10 and
    13,-6 - refer to the center of the bottom-left and top-right
    pixels:

    >>> tr_cen = imextent(img, 10, 13, -10, -6, limits='center')

    The alternative is limits='edge', where 10,-10 refers to the
    bottom-left corner of the image and 13,-6 refers to the
    top-right corner:

    >>> tr_edge = imextent(img, 10, 13, -10, -6, limits='edge')

    >>> print(tr_cen.apply([[1.0, 1.0]]))
    [[ 10. -10.]]
    >>> print(tr_edge.apply([[1.0, 1.0]]))
    [[ 10.375       -9.33333333]]

    """

    try:
        (ny, nx) = img.shape
    except AttributeError:
        raise ValueError("First argument has no shape attribute.")

    dx = (xmax - xmin) * 1.0
    dy = (ymax - ymin) * 1.0

    if limits == 'center':
        dx /= (nx - 1.0)
        dy /= (ny - 1.0)
        x0 = xmin - dx
        y0 = ymin - dy

    elif limits == 'edge':
        dx /= nx
        dy /= ny
        x0 = xmin - dx / 2.0
        y0 = ymin - dy / 2.0

    else:
        raise ValueError("limits must be 'center' or 'edge', not '{}'".format(limits))

    tr = LINEAR2DTransform()

    tr.get_parameter('ROTATION').set_value(0.0)
    tr.get_parameter('SCALE').set_value([dx, dy])
    tr.get_parameter('OFFSET').set_value([x0, y0])

    return tr
