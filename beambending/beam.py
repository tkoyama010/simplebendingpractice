"""Main module containing the main class Beam, and auxiliary classes PointLoad 
and DistributedLoad.

Example
-------
>>> my_beam = Beam(9)
>>> my_beam.fixed_support = 2    # x-coordinate of the fixed support
>>> my_beam.rolling_support = 7  # x-coordinate of the rolling support
>>> my_beam.add_loads([PointLoad(-20, 3)])  # 20kN downwards, at x=3m
>>> print("(F_Ax, F_Ay, F_By) =", my_beam.get_reaction_forces())
(F_Ax, F_Ay, F_By) = (0.0, 16.0, 4.0)
>>> my_beam.plot()
<Figure size 600x1000 with 3 Axes>

"""

from collections import namedtuple
from contextlib import contextmanager
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle
import numpy as np
import os
import sympy
from sympy import integrate

# plt.rc('text', usetex=True)  # This makes the plot text prettier... but SLOWER


class PointLoad(namedtuple("PointLoad", "force, coord")):
    """Point load described by a tuple of floats: (force, coord).

    Examples
    --------
    >>> external_force = PointLoad(-30, 3)  # 30kN downwards at x=3m
    """


class DistributedLoad(namedtuple("DistributedLoad", "expr, span")):
    """Distributed load, described by its functional form and application interval.

    Examples
    --------
    >>> snow_load = DistributedLoad("10*x+5", (0, 2))  # Linearly growing load for 0<x<2
    """


class Beam:
    """
    Represents a one-dimensional beam that can take axial and tangential loads.
    
    A Beam object can accept as inputs:
    
    * PointLoad objects, and
    * DistributedLoad objects.

    """
    
    def __init__(self, span: float=10):
        """Initializes a Beam object of a given length.

        Parameters
        ----------
        span : float or int
            Length of the beam span. Must be positive, and the fixed and rolling
            supports can only be placed within this span. The default value is 10.

        """
        self._x0 = 0
        self._x1 = span
        self._fixed_support = 2
        self._rolling_support = 8

        self._loads = []
        self._distributed_forces = []
        self._shear_forces = []
        self._bending_moments = []

    @property
    def length(self):
        """float or int: Length of the beam. Must be positive."""
        return self._x1 - self._x0
        
    @length.setter
    def length(self, length: float):
        if length > 0:
            self._x1 = self._x0 + length
        else:
            raise ValueError("The provided length must be positive.")

    @property
    def fixed_support(self):
        """float or int: x-coordinate of the beam's fixed support. Must be 
        within the beam span."""
        return self._fixed_support

    @fixed_support.setter
    def fixed_support(self, x_coord: float):
        if self._x0 <= x_coord <= self._x1:
            self._fixed_support = x_coord
        else:
            raise ValueError("The fixed support must be located within the beam span.")

    @property
    def rolling_support(self):
        """float or int: x-coordinate of the beam's rolling support. Must be 
        within the beam span."""
        return self._rolling_support

    @rolling_support.setter
    def rolling_support(self, x_coord: float):
        if self._x0 <= x_coord <= self._x1:
            self._rolling_support = x_coord
        else:
            raise ValueError("The rolling support must be located within the beam span.")

    def add_loads(self, loads: list):
        """Apply an arbitrary list of (point- or distributed) loads to the beam.

        Parameters
        ----------
        loads : iterable
            An iterable containing DistributedLoad or PointLoad objects to
            be applied to the Beam object. Note that the load application point
            (or segment) must be within the Beam span.

        """
        for load in loads:
            if isinstance(load, (DistributedLoad, PointLoad)):
                self._loads.append(load)
            else:
                raise TypeError("The provided loads must be of type DistributedLoad or PointLoad")
        self._update_loads()

    def get_reaction_forces(self):
        """
        Calculates the reaction forces at the supports, given the applied loads.
        
        The first and second values correspond to the horizontal and vertical 
        forces of the fixed support. The third one is the vertical force at the
        rolling support.

        Returns
        -------
        F_Ax, F_Ay, F_By: (float, float, float)
            reaction force components for fixed (x,y) and rolling (y) supports 
            respectively.

        """
        x = sympy.symbols("x")
        x0, x1 = self._x0, self._x1
        xA, xB = self._fixed_support, self._rolling_support
        F_Rx = 0
        F_Ry = sum(integrate(load, (x, x0, x1)) for load in self._distributed_forces) + \
               sum(f.force for f in self._point_loads())
        M_R = sum(integrate(load * x, (x, x0, x1)) for load in self._distributed_forces) + \
              sum(f.force * f.coord for f in self._point_loads())
        A = np.array([[-1, 0, 0],
                      [0, -1, -xA],
                      [0, -1, -xB]]).T
        b = np.array([F_Rx, F_Ry, M_R])
        F_Ax, F_Ay, F_By = np.linalg.inv(A).dot(b)
        return F_Ax, F_Ay, F_By

    def plot(self):
        """Plots the loaded beam, with shear force and bending moment diagrams.

        Returns
        -------
        figure : `~matplotlib.figure.Figure`
            Returns a handle to a figure with the 3 subplots: Beam schematic, 
            shear force diagram, and bending moment diagram.

        """
        fig = plt.figure(figsize=(6, 10))
        fig.subplots_adjust(hspace=0.4)

        # TODO: Take care of beam plotting
        ax1 = fig.add_subplot(3, 1, 1)
        ax1.set_title("Loaded beam diagram")

        plot01_params = {'ylabel': "Beam loads", 'yunits': r'kN / m',
                         # 'xlabel':"Beam axis", 'xunits':"m",
                         'color': "b",
                         'inverted': True}
        self._plot_analytical(ax1, sum(self._distributed_forces), **plot01_params)
        self._draw_beam_schematic(ax1)

        ax2 = fig.add_subplot(3, 1, 2)
        plot02_params = {'ylabel': "Shear force", 'yunits': r'kN',
                         # 'xlabel':"Beam axis", 'xunits':"m",
                         'color': "r"}
        self._plot_analytical(ax2, sum(self._shear_forces), **plot02_params)

        ax3 = fig.add_subplot(3, 1, 3)
        plot03_params = {'ylabel': "Bending moment", 'yunits': r'kN \cdot m',
                         'xlabel': "Beam axis", 'xunits': "m",
                         'color': "y"}
        self._plot_analytical(ax3, sum(self._bending_moments), **plot03_params)

        return fig

    def _plot_analytical(self, ax: plt.axes, sym_func, title: str = "", maxmin_hline: bool = True, xunits: str = "",
                        yunits: str = "", xlabel: str = "", ylabel: str = "", color=None, inverted=False):
        """
        Auxiliary function for plotting a sympy.Piecewise analytical function.

        :param ax: a matplotlib.Axes object where the data is to be plotted.
        :param x_vec: array-like, support where the provided symbolic function will be plotted
        :param sym_func: symbolic function using the variable x
        :param title: title to show above the plot, optional
        :param maxmin_hline: when set to False, the extreme values of the function are not displayed
        :param xunits: str, physical unit to be used for the x-axis. Example: "m"
        :param yunits: str, physical unit to be used for the y-axis. Example: "m"
        :param xlabel: str, physical variable displayed on the x-axis. Example: "Length"
        :param ylabel: str, physical variable displayed on the y-axis. Example: "Shear force"
        :param color: color to be used for the shaded area of the plot. No shading if not provided
        :return: a matplotlib.Axes object representing the plotted data.

        """
        x = sympy.symbols('x')
        x_vec = np.linspace(self._x0, self._x1, min(int((self.length) * 1000 + 1), 1e4))
        y_vec = sympy.lambdify(x, sym_func, "numpy")(x_vec)
        y_vec *= np.ones(x_vec.shape)

        if inverted:
            y_vec *= -1

        if color:
            a, b = x_vec[0], x_vec[-1]
            verts = [(a, 0)] + list(zip(x_vec, y_vec)) + [(b, 0)]
            poly = Polygon(verts, facecolor=color, edgecolor='0.5', alpha=0.5)
            ax.add_patch(poly)

        if maxmin_hline:
            ax.axhline(y=max(y_vec), linestyle='--', color="g", alpha=0.5)
            max_idx = y_vec.argmax()
            ax.axhline(y=min(y_vec), linestyle='--', color="g", alpha=0.5)
            min_idx = y_vec.argmin()
            plt.annotate('${:0.1f}'.format(y_vec[max_idx]*(1-2*inverted)).rstrip('0').rstrip('.') + " {}$".format(yunits),
                         xy=(x_vec[max_idx], y_vec[max_idx]), xytext=(8, 0), xycoords=('data', 'data'),
                         textcoords='offset points', size=12)
            plt.annotate('${:0.1f}'.format(y_vec[min_idx]*(1-2*inverted)).rstrip('0').rstrip('.') + " {}$".format(yunits),
                         xy=(x_vec[min_idx], y_vec[min_idx]), xytext=(8, 0), xycoords=('data', 'data'),
                         textcoords='offset points', size=12)

        ax.set_xlim([x_vec.min(), x_vec.max()])
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)

        if title:
            ax.set_title(title)

        if xlabel or xunits:
            ax.set_xlabel('{} $[{}]$'.format(xlabel, xunits))

        if ylabel or yunits:
            ax.set_ylabel("{} $[{}]$".format(ylabel, yunits))

        return ax

    def _draw_beam_schematic(self, ax):
        """Auxiliary function for plotting the beam object and its applied loads.
        """
        # Adjust y-axis
        ymin, ymax = -5, 5
        ylim = (min(ax.get_ylim()[0], ymin), max(ax.get_ylim()[1], ymax))
        ax.set_ylim(ylim)
        yspan = ylim[1] - ylim[0]

        # Draw beam body
        beam_left, beam_right = self._x0, self._x1
        beam_length = beam_right - beam_left
        beam_height = yspan * 0.03
        beam_bottom = -1 * beam_height / 2
        beam_top = beam_bottom + beam_height
        beam_body = Rectangle(
            (beam_left, beam_bottom), beam_length, beam_height, fill=True,
            facecolor="black", clip_on=False
        )
        ax.add_patch(beam_body)

        # Draw arrows at point loads
        _f_ax, f_ay, f_by = self.get_reaction_forces()
        fixed_support_load = PointLoad(f_ay, self._fixed_support)
        rolling_support_load = PointLoad(f_by, self._rolling_support)

        for load in (*self._point_loads(),
                     fixed_support_load,
                     rolling_support_load):
            if load[0] < 0:
                y0, y1 = beam_top, beam_top + yspan * 0.17
            else:
                y0, y1 = beam_bottom, beam_bottom - yspan * 0.17
            ax.annotate("",
                        xy=(load[1], y0), xycoords='data',
                        xytext=(load[1], y1), textcoords='data',
                        arrowprops=dict(arrowstyle="simple", color="blue"),
                        )

        ax.spines['left'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)

    def _update_loads(self):
        x = sympy.symbols("x")
        x0 = self._x0

        self._distributed_forces = [self._create_distributed_force(f) for f in self._distributed_loads()]

        _f_ax, f_ay, f_by = self.get_reaction_forces()
        fixed_support_load = PointLoad(f_ay, self._fixed_support)
        rolling_support_load = PointLoad(f_by, self._rolling_support)

        self._shear_forces = [integrate(load, (x, x0, x)) for load in self._distributed_forces]
        self._shear_forces.extend(self._shear_from_pointload(f) for f in self._point_loads())
        self._shear_forces.append(self._shear_from_pointload(fixed_support_load))
        self._shear_forces.append(self._shear_from_pointload(rolling_support_load))

        self._bending_moments = [integrate(load, (x, x0, x)) for load in self._shear_forces]

    def _create_distributed_force(self, load: DistributedLoad, shift: bool=True):
        """
        Create a sympy.Piecewise object representing the provided distributed load.

        :param expr: string with a valid sympy expression.
        :param interval: tuple (x0, x1) containing the extremes of the interval on
        which the load is applied.
        :param shift: when set to False, the x-coordinate in the expression is
        referred to the left end of the beam, instead of the left end of the
        provided interval.
        :return: sympy.Piecewise object with the value of the distributed load.
        """
        expr, interval = load
        x = sympy.symbols("x")
        x0, x1 = interval
        expr = sympy.sympify(expr)
        if shift:
            expr.subs(x, x - x0)
        return sympy.Piecewise((0, x < x0), (0, x > x1), (expr, True))

    def _shear_from_pointload(self, load: PointLoad):
        """
        Create a sympy.Piecewise object representing the shear force caused by a
        point load.

        :param value: float or string with the numerical value of the point load.
        :param coord: x-coordinate on which the point load is applied.
        :return: sympy.Piecewise object with the value of the shear force produced
        by the provided point load.
        """
        value, coord = load
        x = sympy.symbols("x")
        return sympy.Piecewise((0, x < coord), (value, True))

    def _point_loads(self):
        for f in self._loads:
            if isinstance(f, PointLoad):
                yield f

    def _distributed_loads(self):
        for f in self._loads:
            if isinstance(f, DistributedLoad):
                yield f