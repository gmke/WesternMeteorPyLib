""" Loading CAMS file products, FTPDetectInfo and CameraSites files, running the trajectory solver on loaded
    data. 

"""

from __future__ import print_function, division, absolute_import

import os

import numpy as np

from wmpl.Formats.Milig import StationData, writeMiligInputFile
from wmpl.Utils.TrajConversions import J2000_JD, date2JD, equatorialCoordPrecession_vect, raDec2AltAz_vect
from wmpl.Trajectory.Trajectory import Trajectory
from wmpl.Trajectory.GuralTrajectory import GuralTrajectory
from wmpl.Utils.Math import averageClosePoints
from wmpl.Utils.Physics import calcMass


class MeteorObservation(object):
    """ Container for meteor observations. 
        
        The loaded points are RA and Dec in J2000 epoch, in radians.
    """

    def __init__(self, jdt_ref, station_id, latitude, longitude, height, fps):

        self.jdt_ref = jdt_ref
        self.station_id = station_id
        self.latitude = latitude
        self.longitude = longitude
        self.height = height
        self.fps = fps

        self.time_data = []
        self.azim_data = []
        self.elev_data = []
        self.ra_data = []
        self.dec_data = []
        self.mag_data = []
        self.abs_mag_data = []



    def addPoint(self, frame_n, azim, elev, ra, dec, mag):
        """ Adds the measurement point to the meteor.

        Arguments:
            frame_n: [flaot] Frame number from the reference time.
            azim: [float] Azimuth, J2000 in degrees.
            elev: [float] Elevation angle, J2000 in degrees.
            ra: [float] Right ascension, J2000 in degrees.
            dec: [float] Declination, J2000 in degrees.
            mag: [float] Visual magnitude.

        """

        # Calculate the time in seconds w.r.t. to the reference JD
        point_time = frame_n/self.fps

        print('Point time:', point_time)

        self.time_data.append(point_time)

        # Angular coordinates converted to radians
        self.azim_data.append(np.radians(azim))
        self.elev_data.append(np.radians(elev))
        self.ra_data.append(np.radians(ra))
        self.dec_data.append(np.radians(dec))
        self.mag_data.append(mag)



    def finish(self):
        """ When the initialization is done, convert data lists to numpy arrays. """

        self.time_data = np.array(self.time_data)
        self.azim_data = np.array(self.azim_data)
        self.elev_data = np.array(self.elev_data)
        self.ra_data = np.array(self.ra_data)
        self.dec_data = np.array(self.dec_data)



    def __repr__(self):

        out_str = ''

        out_str += 'Station ID = ' + str(self.station_id) + '\n'
        out_str += 'JD ref = {:f}'.format(self.jdt_ref) + '\n'
        out_str += 'lat = {:f}, lon = {:f}, ht = {:f} m'.format(np.degrees(self.latitude), 
            np.degrees(self.longitude), self.height) + '\n'
        out_str += 'FPS = {:f}'.format(self.fps) + '\n'

        out_str += 'Points:\n'
        out_str += 'Time, azimuth, elevation, RA, Dec:\n'

        for point_time, azim, elev, ra, dec in zip(self.time_data, self.azim_data, self.elev_data, \
                self.ra_data, self.dec_data):

            out_str += '{:.4f}, {:.2f}, {:.2f}, {:.2f}, {:+.2f}\n'.format(point_time, np.degrees(azim), \
                np.degrees(elev), np.degrees(ra), np.degrees(dec))


        return out_str





def loadCameraTimeOffsets(cameratimeoffsets_file_name):
    """ Loads time offsets in seconds from the CameraTimeOffsets.txt file. 
    

    Arguments:
        camerasites_file_name: [str] Path to the CameraTimeOffsets.txt file.

    Return:
        time_offsets: [dict] (key, value) pairs of (station_id, time_offset) for every station.
    """


    time_offsets = {}

    with open(cameratimeoffsets_file_name) as f:

        # Skip the header
        for i in range(2):
            next(f)

        # Load camera time offsets
        for line in f:

            line = line.replace('\n', '')
            line = line.split()

            station_id = line[0].strip()

            # Try converting station ID to integer
            try:
                station_id = int(station_id)
            except:
                pass

            t_offset = float(line[1])

            time_offsets[station_id] = t_offset


    return time_offsets




def loadCameraSites(camerasites_file_name):
    """ Loads locations of cameras from a CAMS-style CameraSites files. 

    Arguments:
        camerasites_file_name: [str] Path to the CameraSites.txt file.

    Return:
        stations: [dict] A dictionary where the keys are stations IDs, and values are lists of:
            - latitude +N in radians
            - longitude +E in radians
            - height in meters
    """


    stations = {}

    with open(camerasites_file_name) as f:

        # Skip the fist two lines (header)
        for i in range(2):
            next(f)

        # Read in station info
        for line in f:

            # Skip commended out lines
            if line[0] == '#':
                continue

            line = line.replace('\n', '')

            if line:

                line = line.split()

                station_id, lat, lon, height = line[:4]

                station_id = station_id.strip()

                # Try converting station ID to integer
                try:
                    station_id = int(station_id)
                except:
                    pass

                lat, lon, height = map(float, [lat, lon, height])

                stations[station_id] = [np.radians(lat), np.radians(-lon), height*1000]


    return stations




def loadFTPDetectInfo(ftpdetectinfo_file_name, stations, time_offsets=None):
    """

    Arguments:
        ftpdetectinfo_file_name: [str] Path to the FTPdetectinfo file.
        stations: [dict] A dictionary where the keys are stations IDs, and values are lists of:
            - latitude +N in radians
            - longitude +E in radians
            - height in meters
        

    Keyword arguments:
        time_offsets: [dict] (key, value) pairs of (stations_id, time_offset) for every station. None by 
            default.


    Return:
        meteor_list: [list] A list of MeteorObservation objects filled with data from the FTPdetectinfo file.

    """

    meteor_list = []

    with open(ftpdetectinfo_file_name) as f:

        # Skip the header
        for i in range(11):
            next(f)


        current_meteor = None

        bin_name = False
        cal_name = False
        meteor_header = False

        for line in f:

            line = line.replace('\n', '').replace('\r', '')

            # Skip the line if it is empty
            if not line:
                continue


            if '-----' in line:

                # Mark that the next line is the bin name
                bin_name = True

                # If the separator is read in, save the current meteor
                if current_meteor is not None:
                    current_meteor.finish()
                    meteor_list.append(current_meteor)

                continue


            if bin_name:

                bin_name = False

                # Mark that the next line is the calibration file name
                cal_name = True

                # Extract the reference time from the FF bin file name
                line = line.split('_')

                # Count the number of string segments, and determine if it the old or new CAMS format
                if len(line) == 6:
                    sc = 1
                else:
                    sc = 0

                ff_date = line[1 + sc]
                ff_time = line[2 + sc]
                milliseconds = line[3 + sc]

                year = ff_date[:4]
                month = ff_date[4:6]
                day = ff_date[6:8]

                hour = ff_time[:2]
                minute = ff_time[2:4]
                seconds = ff_time[4:6]

                year, month, day, hour, minute, seconds, milliseconds = map(int, [year, month, day, hour, 
                    minute, seconds, milliseconds])

                # Calculate the reference JD time
                jdt_ref = date2JD(year, month, day, hour, minute, seconds, milliseconds)

                continue


            if cal_name:

                cal_name = False

                # Mark that the next line is the meteor header
                meteor_header = True

                continue


            if meteor_header:

                meteor_header = False

                line = line.split()

                # Get the station ID and the FPS from the meteor header
                station_id = line[0].strip()
                fps = float(line[3])

                # Try converting station ID to integer
                try:
                    station_id = int(station_id)
                except:
                    pass

                # If the time offsets were given, apply the correction to the JD
                if time_offsets is not None:

                    if station_id in time_offsets:
                        print('Applying time offset for station {:s} of {:.2f} s'.format(station_id, \
                            time_offsets[station_id]))

                        jdt_ref += time_offsets[station_id]/86400.0

                    else:
                        print('Time offset for given station not found!')


                # Get the station data
                if station_id in stations:
                    lat, lon, height = stations[station_id]


                else:
                    print('ERROR! No info for station ', station_id, ' found in CameraSites.txt file!')
                    print('Exiting...')
                    break


                # Init a new meteor observation
                current_meteor = MeteorObservation(jdt_ref, station_id, lat, lon, height, fps)

                continue


            # Read in the meteor observation point
            if (current_meteor is not None) and (not bin_name) and (not cal_name) and (not meteor_header):

                line = line.replace('\n', '').split()

                # Read in the meteor frame, RA and Dec
                frame_n = float(line[0])
                ra = float(line[3])
                dec = float(line[4])
                azim = float(line[5])
                elev = float(line[6])

                # Read the visual magnitude, if present
                if len(line) > 7:
                    
                    mag = line[8]

                    if mag == 'inf':
                        mag = None

                    else:
                        mag = float(mag)

                else:
                    mag = None


                # Add the measurement point to the current meteor 
                current_meteor.addPoint(frame_n, azim, elev, ra, dec, mag)


        # Add the last meteor the the meteor list
        if current_meteor is not None:
            current_meteor.finish()
            meteor_list.append(current_meteor)


    return meteor_list




def prepareObservations(meteor_list):
    """ Takes a list of MeteorObservation objects, normalizes all data points to the same reference Julian 
        date, precesses the observations from J2000 to the epoch of date. 
    
    Arguments:
        meteor_list: [list] List of MeteorObservation objects

    Return:
        (jdt_ref, meteor_list):
            - jdt_ref: [float] reference Julian date for which t = 0
            - meteor_list: [list] A list a MeteorObservations whose time is normalized to jdt_ref, and are
                precessed to the epoch of date

    """

    if meteor_list:

        # The first meteor is the reference one, normalize the first point to have t = 0, and set the JD to 
        # that point
        ref_ind = 0
        tsec_delta = meteor_list[ref_ind].time_data[0] 
        jdt_delta = tsec_delta/86400.0


        ### Normalize all times to the beginning of the first meteor

        # Apply the normalization to the reference meteor
        meteor_list[ref_ind].jdt_ref += jdt_delta
        meteor_list[ref_ind].time_data -= tsec_delta


        meteor_list_tcorr = []

        for i, meteor in enumerate(meteor_list):

            # Only correct non-reference meteors
            if i != ref_ind:

                # Calculate the difference between the reference and the current meteor
                jdt_diff = meteor.jdt_ref - meteor_list[ref_ind].jdt_ref
                tsec_diff = jdt_diff*86400.0

                # Normalize all meteor times to the same reference time
                meteor.jdt_ref -= jdt_diff
                meteor.time_data += tsec_diff

            meteor_list_tcorr.append(meteor)

        ######

        # The reference JD for all meteors is thus the reference JD of the first meteor
        jdt_ref = meteor_list_tcorr[ref_ind].jdt_ref


        ### Precess observations from J2000 to the epoch of date
        meteor_list_epoch_of_date = []
        for meteor in meteor_list_tcorr:

            jdt_ref_vect = np.zeros_like(meteor.ra_data) + jdt_ref

            # Precess from J2000 to the epoch of date
            ra_prec, dec_prec = equatorialCoordPrecession_vect(J2000_JD.days, jdt_ref_vect, meteor.ra_data, 
                meteor.dec_data)

            meteor.ra_data = ra_prec
            meteor.dec_data = dec_prec

            # Convert preccesed Ra, Dec to altitude and azimuth
            meteor.azim_data, meteor.elev_data = raDec2AltAz_vect(meteor.ra_data, meteor.dec_data, jdt_ref,
                meteor.latitude, meteor.longitude)

            meteor_list_epoch_of_date.append(meteor)


        ######


        return jdt_ref, meteor_list_epoch_of_date

    else:
        return None, None



def solveTrajectoryCAMS(meteor_list, output_dir, solver='original', **kwargs):
    """ Feed the list of meteors in the trajectory solver. """


    # Normalize the observations to the same reference Julian date and precess them from J2000 to the 
    # epoch of date
    jdt_ref, meteor_list = prepareObservations(meteor_list)


    if meteor_list is not None:

        for meteor in meteor_list:
            print(meteor)


        # Init the trajectory solver
        if solver == 'original':
            #traj = Trajectory(jdt_ref, output_dir=output_dir, meastype=1)
            traj = Trajectory(jdt_ref, output_dir=output_dir, meastype=2, **kwargs)

        elif solver == 'gural':
            traj = GuralTrajectory(len(meteor_list), jdt_ref, velmodel=3, meastype=2, verbose=1, 
                output_dir=output_dir)

        else:
            print('No such solver:', solver)
            return 


        # Add meteor observations to the solver
        for meteor in meteor_list:

            if solver == 'original':

                # traj.infillTrajectory(meteor.ra_data, meteor.dec_data, meteor.time_data, meteor.latitude, 
                #     meteor.longitude, meteor.height, station_id = meteor.station_id)

                traj.infillTrajectory(meteor.azim_data, meteor.elev_data, meteor.time_data, meteor.latitude, 
                     meteor.longitude, meteor.height, station_id = meteor.station_id)

            elif solver == 'gural':

                # traj.infillTrajectory(meteor.ra_data, meteor.dec_data, meteor.time_data, meteor.latitude, 
                #     meteor.longitude, meteor.height)

                traj.infillTrajectory(meteor.azim_data, meteor.elev_data, meteor.time_data, meteor.latitude, 
                    meteor.longitude, meteor.height)


        # Solve the trajectory
        traj.run()

        return traj



def cams2MiligInput(meteor_list, file_path):
    """ Writes CAMS data to MILIG input file. 
    
    Arguments:
        meteor_list: [list] A list of MeteorObservation objects.
        file_path: [str] Path to the MILIG input file which will be written.

    Return:
        None
    """

    # Normalize the observations to the same reference Julian date and precess them from J2000 to the 
    # epoch of date
    jdt_ref, meteor_list = prepareObservations(meteor_list)

    ### Convert CAMS MeteorObservation to MILIG StationData object
    milig_list = []
    for i, meteor in enumerate(meteor_list):

        # Check if the station ID is an integer
        try:
            station_id = int(meteor.station_id)

        except ValueError:
            station_id = i + 1

        # Init a new MILIG meteor data container
        milig_meteor = StationData(station_id, meteor.longitude, meteor.latitude, meteor.height)

        # Fill in meteor points
        for azim, elev, t in zip(meteor.azim_data, meteor.elev_data, meteor.time_data):

            # Convert +E of due N azimuth to +W of due S
            milig_meteor.azim_data.append((azim + np.pi)%(2*np.pi))

            # Convert elevation angle to zenith angle
            milig_meteor.zangle_data.append(np.pi/2 - elev)
            milig_meteor.time_data.append(t)


        milig_list.append(milig_meteor)

    ######


    # Write MILIG input file
    writeMiligInputFile(jdt_ref, milig_list, file_path)



def computeAbsoluteMagnitudes(traj, meteor_list):
    """ Given the trajectory, compute the absolute mangitude (visual mangitude @100km). """

    # Go though every observation of the meteor
    for i, meteor_obs in enumerate(meteor_list):

        # Go through all magnitudes and compute absolute mangitudes
        for dist, mag in zip(traj.observations[i].model_range, meteor_obs.mag_data):

            # Skip nonexistent magnitudes
            if mag is not None:
                
                # Compute the range-corrected magnitude
                abs_mag = mag + 5*np.log10((10**5)/dist)

            else:
                abs_mag = None


            meteor_obs.abs_mag_data.append(abs_mag)

        



if __name__ == "__main__":

    import matplotlib.pyplot as plt

    #dir_path = "../DenisGEMcases"
    #dir_path = "../DenisGEMcases_5_sigma"
    #dir_path = "/home/dvida/DATA/Dropbox/Apps/VSA2017 RMS data/first_rpi_orbit"
    #dir_path = "D:/Dropbox/Apps/VSA2017 RMS data/first_rpi_orbit"
    #dir_path = "/home/dvida/DATA/Dropbox/Apps/VSA2017 RMS data/first_rpi_orbit"
    dir_path = "D:/Dropbox/RPi Meteor Station/orbit_test"
    #dir_path = "/home/dvida/Dropbox/RPi Meteor Station/orbit_test"
    #dir_path = "/home/dvida/Dropbox/RPi Meteor Station/orbit_test/20180615_long_shallow_meteor"
    #dir_path = "D:/Dropbox/RPi Meteor Station/orbit_test/20180615_long_shallow_meteor"

    # Find the absolute path of the given directory
    dir_path = os.path.abspath(dir_path)

    camerasites_file_name = 'CameraSites.txt'
    cameratimeoffsets_file_name = 'CameraTimeOffsets.txt'
    #ftpdetectinfo_file_name = 'FTPdetectinfo20121213S.txt'
    #ftpdetectinfo_file_name = 'FTPdetectinfo_first_rpi.txt'
    #ftpdetectinfo_file_name = 'FTPdetectinfo_20180614.txt'
    #ftpdetectinfo_file_name = "FTPdetectinfo_20180614_temporal.txt"
    ftpdetectinfo_file_name = "FTPdetectinfo_20180614_spatial.txt"
    #ftpdetectinfo_file_name = 'FTPdetectinfo_20180615.txt'
    #ftpdetectinfo_file_name = 'FTPdetectinfo_20180615_long_shallow_meteor.txt'


    camerasites_file_name = os.path.join(dir_path, camerasites_file_name)
    cameratimeoffsets_file_name = os.path.join(dir_path, cameratimeoffsets_file_name)
    ftpdetectinfo_file_name = os.path.join(dir_path, ftpdetectinfo_file_name)

    # Get locations of stations
    stations = loadCameraSites(camerasites_file_name)

    # Get time offsets of cameras
    time_offsets = loadCameraTimeOffsets(cameratimeoffsets_file_name)

    # Get the meteor data
    meteor_list = loadFTPDetectInfo(ftpdetectinfo_file_name, stations, time_offsets=time_offsets)


    # Construct lists of observations of the same meteor (Rpi)
    meteor1 = meteor_list[:2]
    meteor2 = meteor_list[2:4]
    meteor3 = meteor_list[4:6]
    meteor4 = meteor_list[6:8]
    meteor5 = meteor_list[8:10]
    meteor6 = meteor_list[10:12]

    # # # Construct lists of observations of the same meteor
    # meteor5 = meteor_list[:2]
    # meteor2 = meteor_list[2:5]
    # meteor6 = meteor_list[5:9]
    # meteor3 = meteor_list[9:13]
    # meteor1 = meteor_list[13:18]
    # meteor4 = meteor_list[18:24]


    # for met in meteor1:
    #   print('--------------------------')
    #   print(met)

    meteor = meteor6

    # Run the trajectory solver
    traj = solveTrajectoryCAMS(meteor, os.path.join(dir_path, 'meteor6_spatial'), solver='original', monte_carlo=False, \
        show_plots=False, save_results=True, mc_noise_std=1.0, mc_runs=250, max_toffset=60.0)


    # ### PERFORM PHOTOMETRY

    # # Compute absolute mangitudes
    # computeAbsoluteMagnitudes(traj, meteor)

    # # List of photometric uncertainties per station
    # photometry_stddevs = [0.3]*len(meteor)
    # # photometry_stddevs = [0.2, 0.3]*len(meteor)

    # time_data_all = []
    # abs_mag_data_all = []

    # # Plot absolute magnitudes for every station
    # for i, (meteor_obs, photometry_stddev) in enumerate(zip(meteor, photometry_stddevs)):

    #     # Take only magnitudes that are not None
    #     good_mag_indices = [j for j, abs_mag in enumerate(meteor_obs.abs_mag_data) if abs_mag is not None]
    #     time_data = traj.observations[i].time_data[good_mag_indices]
    #     abs_mag_data = np.array(meteor_obs.abs_mag_data)[good_mag_indices]

    #     time_data_all += time_data.tolist()
    #     abs_mag_data_all += abs_mag_data.tolist()

    #     # Sort by time
    #     temp_arr = np.c_[time_data, abs_mag_data]
    #     temp_arr = temp_arr[np.argsort(temp_arr[:, 0])]
    #     time_data, abs_mag_data = temp_arr.T

    #     # Plot the magnitude
    #     plt_hande = plt.plot(time_data, abs_mag_data, label=meteor_obs.station_id, zorder=3)

    #     # Plot magnitude errorbars
    #     plt.errorbar(time_data, abs_mag_data, yerr=photometry_stddev, fmt='--o', color=plt_hande[0].get_color())

    
    # plt.legend()

    # plt.xlabel('Time (s)')
    # plt.ylabel('Absolute magnitude')
    
    # plt.gca().invert_yaxis()

    # plt.grid()

    # plt.show()


    # ### Compute the mass

    # # Sort by time
    # temp_arr = np.c_[time_data_all, abs_mag_data_all]
    # temp_arr = temp_arr[np.argsort(temp_arr[:, 0])]
    # time_data_all, abs_mag_data_all = temp_arr.T

    # # Average the close points
    # time_data_all, abs_mag_data_all = averageClosePoints(time_data_all, abs_mag_data_all, 1/(2*25))

    # time_data_all = np.array(time_data_all)
    # abs_mag_data_all = np.array(abs_mag_data_all)

    # # Compute the mass
    # mass = calcMass(time_data_all, abs_mag_data_all, traj.v_avg, P_0m=1210)

    # print(mass)

    # ######



    ############################


    # Write the MILIG input file
    #cams2MiligInput(meteor6, 'milig_meteor6.txt')
