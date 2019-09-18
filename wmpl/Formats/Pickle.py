""" Reruns the trajectory solution from a trajectory pickle file. """

from __future__ import print_function, division, absolute_import

import os
import sys

import numpy as np

from wmpl.Formats.EvUWO import writeEvFile
from wmpl.Utils.Pickling import loadPickle
from wmpl.Utils.TrajConversions import jd2Date
from wmpl.Trajectory.Trajectory import Trajectory
from wmpl.Trajectory.GuralTrajectory import GuralTrajectory


def dumpAsEvFiles(dir_path, file_name):
    """ Dump the given pickle file as UWO-style ev_* file. """

        # Load the pickles trajectory
    traj = loadPickle(dir_path, file_name)

    
    # Dump the results as a UWO-style ev file

    year, month, day, hour, minute, second, _ = jd2Date(traj.jdt_ref)

    for i, obs in enumerate(traj.observations):

        # Construct file name
        date_str = "{:4d}{:02d}{:02d}_{:02d}{:02d}{:02d}A_{:s}".format(year, month, day, hour, minute, second, \
            obs.station_id)

        ev_file_name = 'ev_' + date_str + '.txt'

        # Convert azimuth and altitude to theta/tphi
        theta_data = np.pi/2.0 - obs.elev_data
        phi_data = (np.pi/2.0 - obs.azim_data)%(2*np.pi)

        # Write the ev_* file
        writeEvFile(dir_path, ev_file_name, traj.jdt_ref, str(i), obs.lat, obs.lon, obs.ele, 
            obs.time_data, theta_data, phi_data)




def solveTrajectoryPickle(dir_path, file_name, only_plot=False, solver='original', **kwargs):
    """ Rerun the trajectory solver on the given trajectory pickle file. """


    # Load the pickles trajectory
    traj_p = loadPickle(dir_path, file_name)

    # Run the PyLIG trajectory solver
    if solver == 'original':

        # Given the max time offset from the pickle file and input, use the larger one of the two
        max_toffset = traj_p.max_toffset
        if "max_toffset" in kwargs:

            if (kwargs["max_toffset"] is not None) and (traj_p.max_toffset is not None):

                max_toffset = max(traj_p.max_toffset, kwargs["max_toffset"])

            # Remove the max time offset from the list of keyword arguments
            kwargs.pop("max_toffset", None)


        # Reinitialize the trajectory solver
        traj = Trajectory(traj_p.jdt_ref, output_dir=dir_path, max_toffset=max_toffset, \
            meastype=traj_p.meastype, **kwargs)


        # Fill the observations
        for i, obs in enumerate(traj_p.observations):

            # Check if the trajectory had any excluded points
            if hasattr(traj_p, 'excluded_time'):
                excluded_time = obs.excluded_time

            else:
                excluded_time = None


            traj.infillTrajectory(obs.meas1, obs.meas2, obs.time_data, obs.lat, obs.lon, obs.ele, 
                station_id=obs.station_id, excluded_time=excluded_time, ignore_list=obs.ignore_list)


    elif solver == 'gural':

        # Init the Gural solver
        # traj = GuralTrajectory(len(traj_p.observations), traj_p.jdt_ref, max_toffset=traj_p.max_toffset, \
        #     meastype=traj_p.meastype, output_dir=dir_path)

        traj = GuralTrajectory(len(traj_p.observations), traj_p.jdt_ref, velmodel=3, \
            max_toffset=traj_p.max_toffset, meastype=traj_p.meastype, output_dir=dir_path, verbose=True)


        # Fill the observations
        for obs in traj_p.observations:

            traj.infillTrajectory(obs.meas1, obs.meas2, obs.time_data, obs.lat, obs.lon, obs.ele)


    else:
        print('Unrecognized solver:', solver)



    if only_plot:

        # Disable saving plots
        traj_p.save_results = False

        # Show the plots
        traj_p.savePlots(None, None, show_plots=True)


    # Recompute the trajectory
    else:
        
        # Run the trajectory solver
        traj.run()


    return traj




if __name__ == "__main__":


    import argparse


    ### COMMAND LINE ARGUMENTS

    # Init the command line arguments parser
    arg_parser = argparse.ArgumentParser(description=""" Re-run the Monte Carlo trajectory solver on a trajectory pickle file.""",
        formatter_class=argparse.RawTextHelpFormatter)

    arg_parser.add_argument('input_file', type=str, help='Path to the .pickle file.')

    arg_parser.add_argument('-a', '--onlyplot', \
        help='Do not recompute the trajectory, just show the plots.', action="store_true")

    arg_parser.add_argument('-s', '--solver', metavar='SOLVER', help="""Trajectory solver to use. \n
        - 'original' - Monte Carlo solver
        - 'gural0' - Gural constant velocity
        - 'gural1' - Gural linear deceleration
        - 'gural2' - Gural quadratic deceleration
        - 'gural3' - Gural exponential deceleration
         """, type=str, nargs='?', default='original')

    arg_parser.add_argument('-t', '--maxtoffset', metavar='MAX_TOFFSET', nargs=1, \
        help='Maximum time offset between the stations.', type=float)

    arg_parser.add_argument('-v', '--vinitht', metavar='V_INIT_HT', nargs=1, \
        help='The initial veloicty will be estimated as the average velocity above this height (in km). If not given, the initial velocity will be estimated using the sliding fit which can be controlled with the --velpart option.', \
        type=float)

    arg_parser.add_argument('-p', '--velpart', metavar='VELOCITY_PART', \
        help='Fixed part from the beginning of the meteor on which the initial velocity estimation using the sliding fit will start. Default is 0.25 (25 percent), but for noisier data this might be bumped up to 0.5.', \
        type=float, default=0.25)

    arg_parser.add_argument('-d', '--disablemc', \
        help='Do not use the Monte Carlo solver, but only run the geometric solution.', action="store_true")
    
    arg_parser.add_argument('-r', '--mcruns', metavar="MC_RUNS", nargs='?', \
        help='Number of Monte Carlo runs.', type=int, default=100)

    arg_parser.add_argument('-u', '--uncertgeom', \
        help='Compute purely geometric uncertainties.', action="store_true")
    
    arg_parser.add_argument('-g', '--disablegravity', \
        help='Disable gravity compensation.', action="store_true")

    arg_parser.add_argument('-l', '--plotallspatial', \
        help='Plot a collection of plots showing the residuals vs. time, length and height.', \
        action="store_true")

    arg_parser.add_argument('-i', '--imgformat', metavar='IMG_FORMAT', nargs=1, \
        help="Plot image format. 'png' by default, can be 'pdf', 'eps',... ", type=str, default='png')

    arg_parser.add_argument('-x', '--hideplots', \
        help="Don't show generated plots on the screen, just save them to disk.", action="store_true")

    # Parse the command line arguments
    cml_args = arg_parser.parse_args()

    ############################
    

    ### Parse command line arguments ###

    max_toffset = None
    print(cml_args.maxtoffset)
    if cml_args.maxtoffset:
        max_toffset = cml_args.maxtoffset[0]

    velpart = None
    if cml_args.velpart:
        velpart = cml_args.velpart

    vinitht = None
    if cml_args.vinitht:
        vinitht = cml_args.vinitht[0]

    ### ###

        
    # Split the input directory and the file
    if os.path.isfile(cml_args.input_file):

        dir_path, file_name = os.path.split(cml_args.input_file)

    else:
        print('Input file: {:s}'.format(cml_args.input_file))
        print('The given input file does not exits!')
        sys.exit()

    # Run the solver
    solveTrajectoryPickle(dir_path, file_name, only_plot=cml_args.onlyplot, solver=cml_args.solver, \
        max_toffset=max_toffset, monte_carlo=(not cml_args.disablemc), mc_runs=cml_args.mcruns, \
        geometric_uncert=cml_args.uncertgeom, gravity_correction=(not cml_args.disablegravity), \
        plot_all_spatial_residuals=cml_args.plotallspatial, plot_file_type=cml_args.imgformat, \
        show_plots=(not cml_args.hideplots), v_init_part=velpart, v_init_ht=vinitht)