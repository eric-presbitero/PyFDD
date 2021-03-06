
from pyfdd import Lib2dl, PatternCreator, DataPattern, FitManager
from pyfdd.patterncreator import create_detector_mesh

import numpy as np
import matplotlib.pyplot as plt


def make_tpx_pattern(lib, patterns=(1,), name = 'temp_tpx.json'):

    xmesh, ymesh = create_detector_mesh(512, 512, 0.055, 300)
    # 5 subpixels is a good number for the pads
    gen = PatternCreator(lib, xmesh, ymesh, simulations=patterns, sub_pixels=1)

    fractions_per_sim = np.array([1])
    #fractions_per_sim /= fractions_per_sim.sum()
    total_events = 0.3 * 512**2
    pattern = gen.make_pattern(0.0, 0.0, 0, fractions_per_sim, total_events, sigma=0, type='montecarlo')
    print(pattern.sum())

    # create medipix matrix
    mm = DataPattern(pattern_array=pattern)
    mm.manip_create_mesh(pixel_size=0.055, distance=300)

    return mm


if __name__ == '__main__':
    lib = Lib2dl("/home/eric/cernbox/University/CERN-projects/Betapix/Analysis/Channeling_analysis/FDD_libraries/GaN_89Sr/ue567g54.2dl")
    mm = make_tpx_pattern(lib)
    mm.set_fit_region(distance=2, angle=45)

    fm = FitManager(cost_function='ml', n_sites=5, sub_pixels=1)
    fm.set_pattern(mm, lib)
    #fm.set_fixed_values(dx=0, dy=0, sigma=0.1)  # pad=0.094, tpx=0.064
    #fm.set_bounds(phi=(-20,20))
    fm.set_step_modifier(dx=.01, dy=.01, phi=.10, sigma=.001, total_cts=0.01, f_p1=.01, f_p2=.01)
    fm.set_initial_values(phi=0.5)
    fm.set_minimization_settings(profile='fine')

    # last 248 set to 249
    P1 = np.arange(1,1)#249)
    #fm.run_fits(P1, pass_results=False, verbose=1)
    p1 = np.array([1])
    fm.run_single_fit(p1, 30, 50, 70, 100, verbose_graphics=False)
    #fm.run_fits([1,2],[20,21],[30,31],[50,51],[70,71])
    sim_dp = fm.get_pattern_from_last_fit()
    plt.figure()
    ax = plt.subplot(111)
    sim_dp.draw(ax,percentiles=(0.1,0.99))

    print(fm.df_horizontal)
    plt.figure()
    ax = plt.subplot(111)
    fm.get_datapattern().draw(ax)
    #fm.save_output('tpx_1site_fixed-orientation_test.csv', save_figure=False)
    plt.show(block=True)
