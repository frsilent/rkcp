from time import sleep
from threading import Thread
import math
from datetime import datetime
from functools import partial


from util import get_avail_twr, get_burn_time_for_dv, get_vessel_pitch_heading, angle_between, get_pitch_heading, \
    find_true_impact_time, get_speed_after_time, get_speed_after_distance, get_suicide_burn_time, get_suicide_burn_distance, \
    to_min_sec_str, get_seconds_to_impact, rotate_vector, get_sphere_impact_time_pos
from manager import PitchManager


class State(object):
    _thread = None

    def __init__(self):
        from controller import Controller
        self.ctrl = Controller.get()
        self.init_state()
        self._thread = Thread(target=self._run, args=())
        self._thread.daemon = True
        self._thread.start()

    def init_state(self):
        pass

    def _run(self):
        self.ctrl.state_condition.acquire()
        self.run()
        self.ctrl.state_condition.notify_all()
        self.ctrl.state_condition.release()

    def run(self):
        pass

    def join(self):
        return self._thread.join()


class PreLaunch(State):
    TARGET_ROLL = 0
    # TARGET_ROLL = 180

    def run(self):
        self.ctrl.vessel.control.input_mode = self.ctrl.space_center.ControlInputMode.override

        # Do warning checks here
        # t_minus = 3
        # print 'Launch in:'
        # while t_minus > 0:
        #     print '{}'.format(t_minus)
        #     t_minus -= 1
        #     # sleep(1)
        #
        # print 'Lift off!'
        # print 'setting: {}'.format(AscentState)

        self.ctrl.vessel.control.throttle = 1.0
        self.ctrl.vessel.auto_pilot.engage()
        self.ctrl.vessel.auto_pilot.target_pitch_and_heading(90, 90)
        self.ctrl.vessel.auto_pilot.target_roll = self.TARGET_ROLL

        if self.ctrl.body.name == 'Kerbin':
            self.ctrl.activate_next_stage()
            sleep(1.0)

        self.ctrl.set_NextStateCls(AscentState)


class AscentState(State):
    ALTITUDE_TURN_START = 100
    # ALTITUDE_TARGET = 250000
    ALTITUDE_TARGET = 175000
    # ALTITUDE_TARGET = 100000
    # ALTITUDE_TARGET = 2868740  # geostationary
    # ALTITUDE_TARGET = 11400000  # Mun
    # ALTITUDE_TARGET = 46400000  # Minmus

    LOW_TWR_PITCH = 82.5
    LOW_TWR_BOUND = 1.05

    HIGH_TWR_PITCH = 72.5
    HIGH_TWR_BOUND = 2.5

    def run(self):
        self.ctrl.vessel.auto_pilot.engage()
        self.ctrl.vessel.auto_pilot.target_roll = PreLaunch.TARGET_ROLL

        twr = self.ctrl.get_avail_twr()
        if twr < 1.0:
            print 'ABORT! TWR TOO LOW! {}'.format(twr)

        if twr <= self.LOW_TWR_BOUND:
            self.ctrl.pitch_manager.fixed_point_pitch = self.LOW_TWR_PITCH
        elif self.LOW_TWR_BOUND < twr < self.HIGH_TWR_BOUND:
            pct = (twr - self.LOW_TWR_BOUND) / (self.LOW_TWR_BOUND - self.HIGH_TWR_BOUND)
            self.ctrl.pitch_manager.fixed_point_pitch = self.LOW_TWR_PITCH + pct * (self.LOW_TWR_PITCH - self.HIGH_TWR_PITCH)
        else:
            self.ctrl.pitch_manager.fixed_point_pitch = self.HIGH_TWR_PITCH

        print 'TWR: ', twr
        print 'FIXED PITCH: {}'.format(self.ctrl.pitch_manager.fixed_point_pitch)

        last_second = datetime.now().second

        # conn = self.ctrl.connection

        # class FakeOrbit(object):
        #     def __init__(self, ctrl):
        #         self.ctrl = ctrl
        #         self.next_orbit_stream = self.ctrl.connection.add_stream(getattr, self.ctrl.vessel.orbit, 'next_orbit')
        #
        #     @property
        #     def periapsis_altitude(self):
        #         next_orbit = self.next_orbit_stream()
        #         if next_orbit is not None:
        #             return next_orbit.periapsis_altitude
        #         return float('inf')
        #
        # orbit = FakeOrbit(self.ctrl)

        # next_orbit_stream = self.ctrl.connection.add_stream(getattr, self.ctrl.vessel.orbit, 'next_orbit')
        # # ut_call = conn.get_call(getattr, conn.space_center, 'ut')
        # # next_orbit_call = self.ctrl.connection.get_call(getattr, self.ctrl.vessel.orbit, 'next_orbit')
        # # print next_orbit_call()
        # print ' ... WTF: ', self.ctrl.vessel.orbit.next_orbit
        # # print next_orbit_stream()
        #
        # periapsis_alt = self.ctrl.connection.add_stream(getattr, self.ctrl.vessel.orbit.next_orbit, 'periapsis_altitude')
        # print '...'
        # # periapsis_alt_call = conn.get_call(periapsis_alt)

        i = 0
        while True:
            i += 1
            curr_second = datetime.now().second
            if curr_second != last_second:
                print
                print 'tks:', i
                print 'stms:', self.ctrl._streams_open
                print 'alt:', self.ctrl.altitude
                print 'mach:', self.ctrl.mach
                print 'pitch:', self.ctrl.pitch
                print 'vptch:', self.ctrl.velocity_pitch
                print 'follow:', self.ctrl.pitch_follow
                print 'apoapsis:', self.ctrl.apoapsis_altitude
                print 'periapsis:', self.ctrl.periapsis_altitude
                # print 'test:', periapsis_alt()

                i = 0
                last_second = curr_second
            if self.ctrl.altitude < self.ALTITUDE_TURN_START:
                self.ctrl.pitch_follow = PitchManager.FIXED_UP

            elif self.ctrl.altitude >= self.ALTITUDE_TURN_START:
                if self.ctrl.altitude < 40000:
                    if self.ctrl.mach == 0.0:
                        # No atmo case...
                        if self.ctrl.altitude < 5000:
                            self.ctrl.pitch_follow = PitchManager.FIXED_POINT
                        else:
                            self.ctrl.pitch_follow = PitchManager.ASCENT_SURFACE_PROGRADE
                    elif self.ctrl.mach < 0.65:
                        self.ctrl.pitch_follow = PitchManager.FIXED_POINT
                    elif self.ctrl.velocity_pitch < 25.0 and self.ctrl.pitch < 26.0:
                        self.ctrl.pitch_manager.fixed_point_pitch = 25.0
                        self.ctrl.pitch_follow = PitchManager.FIXED_POINT
                    else:
                        self.ctrl.pitch_follow = PitchManager.ASCENT_SURFACE_PROGRADE
                elif self.ctrl.altitude < 70000:
                    if self.ctrl.time_to_apoapsis < 30.0 and self.ctrl.velocity_pitch < 15.0:
                        self.ctrl.pitch_manager.fixed_point_pitch = 15.0
                        self.ctrl.pitch_follow = PitchManager.FIXED_POINT
                    else:
                        self.ctrl.pitch_follow = PitchManager.ORBIT_PROGRADE
                else:
                    self.ctrl.pitch_follow = PitchManager.ORBIT_PROGRADE

            if 1.85 > self.ctrl.mach > 0.85:
                # print
                # print '-----'
                # print datetime.now().isoformat()
                diff = math.fabs(1.35 - self.ctrl.mach)  # gives num between 0 and 0.50
                mach_diff_pct = (0.50 - diff) / 0.50
                # print datetime.now().isoformat()
                throttle_pct = 1.0 - (math.sin(math.radians(mach_diff_pct * 90)) * 0.50)
                # print datetime.now().isoformat()
                avail_twr = get_avail_twr(self.ctrl)
                # print datetime.now().isoformat()
                min_twr = 2.0
                if throttle_pct * avail_twr > min_twr:
                    self.ctrl.set_throttle(throttle_pct)
                else:
                    if not avail_twr:
                        self.ctrl.set_throttle(1.0)
                    else:
                        throttle_pct = min_twr / avail_twr
                        self.ctrl.set_throttle(throttle_pct)
                # print datetime.now().isoformat()
                # print

                # if self.ctrl.mach > 1.5:
                #     out_of_bucket = True

            if self.ctrl.apoapsis_altitude < self.ALTITUDE_TARGET:
                if self.ctrl.apoapsis_altitude >= self.ALTITUDE_TARGET * 0.985:
                    avail_twr = self.ctrl.get_avail_twr()
                    if avail_twr:
                        self.ctrl.set_throttle(0.25 / avail_twr)
            else:
                self.ctrl.set_throttle(0)

                if self.ctrl.altitude > 70000:
                    self.ctrl.pitch_follow = PitchManager.ORBIT_PROGRADE
                    # dv_circ_burn = self.get_dv_needed_for_circularization()
                    # burn_time_for_circle = get_burn_time_for_dv(dv_circ_burn, self.ctrl)
                    # burn_start_time = self.ctrl.ut + self.ctrl.time_to_apoapsis - (burn_time_for_circle / 2.0)

                    # self.ctrl.set_burn_dv(dv_circ_burn)

                    print 'waiting for burn init'
                    with self.ctrl.burn_manager.burn_init:
                        self.ctrl.set_burn_dv_func(self.get_dv_needed_for_circularization)
                        self.ctrl.set_burn_point_func(self.get_circularization_burn_point)
                        self.ctrl.burn_manager.burn_init.wait()
                    print 'burn init done'

                    # self.ctrl.set_burn_point(self.get_circularization_burn_point())

                    # print 'dv needed: {}'.format(self.ctrl.burn_dv)
                    # print 'burn point: {}'.format(self.ctrl.burn_point)
                    # print 'ut:         {}'.format(self.ctrl.ut)
                    # print 'burn start: {}'.format(self.ctrl.burn_start)
                    # print 'burn time: {}'.format(self.ctrl.burn_time)
                    self.ctrl.space_center.warp_to(self.ctrl.get_burn_start() - 20)

                    self.ctrl.set_NextStateCls(CoastToApoapsis)
                    break

    def get_dv_needed_for_circularization(self):
        # r_ap = current apoapsis radius in meters (and the altitude you will circularize at)
        r_ap = self.ctrl.apoapsis
        # r_pe = current periapsis radius in meters
        r_pe = self.ctrl.periapsis
        # mu = gravitational parameter for the body you are orbiting (3.5316x1012 m3 / s2 for Kerbin)
        mu = self.ctrl.vessel.orbit.body.gravitational_parameter
        # dv_circ_burn = sqrt(mu / r_ap) - sqrt((r_pe * mu) / (r_ap * (r_pe + r_ap) / 2))
        return math.sqrt(mu / r_ap) - math.sqrt((r_pe * mu) / (r_ap * (r_pe + r_ap) / 2.0))

    def get_circularization_burn_point(self):
        return self.ctrl.ut + self.ctrl.time_to_apoapsis



class CoastToApoapsis(State):
    # def init_state(self):
    #     self.dv_circ_burn = get_dv_needed_for_circularization(self.ctrl)
    #     self.burn_time_for_circle = get_burn_time_for_dv(self.dv_circ_burn, self.ctrl)
    #     self.burn_start_time = self.ctrl.ut + self.ctrl.time_to_apoapsis - (self.burn_time_for_circle / 2.0)
    #     self.burn_end_time = self.burn_start_time + self.burn_time_for_circle

    def run(self):
        burn_stop_acquired = False
        print 'COAST'
        self.ctrl.pitch_follow = PitchManager.ORBIT_PROGRADE
        # self.ctrl.vessel.auto_pilot.engage()
        # self.ctrl.vessel.auto_pilot.target_roll = PreLaunch.TARGET_ROLL

        last_second = datetime.now().second
        i = 0

        burn_start = self.ctrl.get_burn_start()

        self.ctrl.vessel.control.rcs = True
        self.ctrl.vessel.auto_pilot.stopping_time = (4.0, 4.0, 4.0)

        while True:
            i += 1
            curr_second = datetime.now().second

            if curr_second != last_second:
                print
                print 'tks:', i
                # print 'alt:', self.ctrl.altitude
                print 'streams:', self.ctrl._streams_open
                print 'follow:', self.ctrl.pitch_follow
                print 'apoapsis:', self.ctrl.apoapsis_altitude
                print 'periapsis:', self.ctrl.periapsis_altitude
                print 'dv:', self.ctrl.burn_dv
                print 'bp:', self.ctrl.burn_point
                print 'bt:', self.ctrl.burn_time
                print 'bs:', self.ctrl.burn_start
                print 'gg:', burn_start
                print 'ut:', self.ctrl.ut
                print 'st:', self.ctrl.connection.space_center.ut
                # print 'be:', self.burn_end_time

                i = 0
                last_second = curr_second

            # # if self.ctrl.time_to_apoapsis > (90 + self.burn_time_for_circle / 2.0 - self.burn_time_for_circle * 0.1):
            # if self.ctrl.ut < burn_start_time - 15:
            #     pass
            #     # self.ctrl.space_center.rails_warp_factor = 3
            # # elif self.ctrl.time_to_apoapsis > (15 + self.burn_time_for_circle / 2.0 - self.burn_time_for_circle * 0.1):
            # elif self.ctrl.ut < burn_start_time:
            #     pass
            #     # self.ctrl.space_center.physics_warp_factor = 4
            # # elif self.ctrl.time_to_apoapsis > (self.burn_time_for_circle / 2.0 - self.burn_time_for_circle * 0.1):
            # # elif self.ctrl.burn_manager.burning:
            #     # self.ctrl.space_center.physics_warp_factor = 0
            #     # self.ctrl.set_throttle(1.0)
            #     # pass
            # else:

            if burn_start:
                if self.ctrl.ut < burn_start - 4:
                    self.ctrl.vessel.auto_pilot.stopping_time = (2.0, 2.0, 2.0)
                elif self.ctrl.ut < burn_start - 2:
                    self.ctrl.vessel.auto_pilot.stopping_time = (0.5, 0.5, 0.5)
                    self.ctrl.vessel.control.rcs = False

                    print 'CoastToApoapsis acquire...'
                    with self.ctrl.burn_manager.burn_end:
                        print 'CoastToApoapsis waiting...'
                        self.ctrl.burn_manager.burn_end.wait()
                        print 'CoastToApoapsis release...'
                        # Maybe some conditional logic here to choose where to go?
                        self.ctrl.set_NextStateCls(InOrbit)
                        break


class InOrbit(State):
    def init_state(self):
        pass

    def run(self):
        self.ctrl.set_NextStateCls(CoastToInterceptBurn)

        # while True:
        #     print 'in orbit!'
        #     sleep(1)
        # pass
        # while True:
        #     if self.burn_start_time < self.ctrl.ut < self.burn_end_time:
        #         self.ctrl.space_center.physics_warp_factor = 0
        #         self.ctrl.set_throttle(1.0)
        #     else:
        #         self.ctrl.set_throttle(0.0)
        #         self.ctrl.vessel.control.rcs = False
        #         self.ctrl.set_NextStateCls(Circularize)
        #         break


class CoastToInterceptBurn(State):
    def init_state(self):
        self.active_body = self.ctrl.space_center.bodies['Kerbin']
        self.target_body = self.ctrl.space_center.bodies['Mun']

    def run(self):
        self.ctrl.target_body = self.target_body

        self.ctrl.pitch_follow = PitchManager.ORBIT_PROGRADE
        self.ctrl.vessel.auto_pilot.engage()
        self.ctrl.vessel.auto_pilot.target_roll = 0

        vessel = self.ctrl.vessel
        # space_center = self.ctrl.space_center

        # orb_flight = vessel.flight(self.ctrl.body.non_rotating_reference_frame)
        # surf_flight = vessel.flight(self.ctrl.active_body.reference_frame)
        mun = self.target_body
        kerbin = self.active_body

        # vi = math.fabs(orb_flight.speed)
        # alt = orb_flight.surface_altitude

        mun_pos = mun.position(kerbin.non_rotating_reference_frame)
        ves_pos = vessel.position(kerbin.non_rotating_reference_frame)
        phase_rads = angle_between(mun_pos, ves_pos)

        # relative_inclination = math.degrees(mun.orbit.relative_inclination(vessel))
        r1 = vessel.orbit.radius
        r2 = mun.orbit.radius
        phase_rad_needed = math.pi * (1 - math.sqrt((1 / 8.0) * (1.0 + (r1 / r2)) ** 3))
        mu = vessel.orbit.body.gravitational_parameter

        # dv_burn = math.sqrt(mu / r1) * (math.sqrt(2 * r2 / (r1 + r2)) - 1)

        # burn_time = get_burn_time_for_dv(dv_burn, vessel)

        speed_r1 = math.sqrt(mu / (r1 ** 3))
        speed_r2 = math.sqrt(mu / (r2 ** 3))
        speed_diff = speed_r2 - speed_r1

        if phase_rad_needed < phase_rads:
            rad_to_burn = phase_rads - phase_rad_needed
        else:
            rad_to_burn = 2 * math.pi + phase_rads - phase_rad_needed

        seconds_until_burn = math.fabs(rad_to_burn / speed_diff)

        # print 'bt: ', burn_time
        # print 'ub: ', seconds_until_burn\

        print 'waiting for burn init'
        with self.ctrl.burn_manager.burn_init:
            self.ctrl.set_burn_dv(math.sqrt(mu / r1) * (math.sqrt(2 * r2 / (r1 + r2)) - 1))
            self.ctrl.set_burn_point(self.ctrl.ut + seconds_until_burn)
            self.ctrl.burn_manager.burn_init.wait()
        print 'burn init done'

        def thread_run(ctrl):
            def next_orbit_change(next_orbit, ctrl):
                ctrl.burn_manager.burn_halt()

            while True:
                sleep(0.1)
                next_orbit = ctrl.vessel.orbit.next_orbit
                if next_orbit is not None:
                    next_orbit_change(next_orbit, ctrl)
                    break

        print 'threads...'
        # next_orbit_stream = self.ctrl.connection.add_stream(getattr, self.ctrl.vessel.orbit, 'next_orbit')
        # next_orbit_stream.add_callback(partial(next_orbit_change_callback, ctrl=self.ctrl))
        # print 'added callback...'
        # next_orbit_stream.start()

        thread = Thread(target=thread_run, args=(self.ctrl,))
        # thread.daemon = True
        thread.start()
        print '...done...'

        self.ctrl.vessel.control.rcs = True
        self.ctrl.vessel.auto_pilot.stopping_time = (4.0, 4.0, 4.0)
        self.ctrl.space_center.warp_to(self.ctrl.get_burn_start() - 20)
        self.ctrl.set_NextStateCls(BurnToBody)
                # break


class BurnToBody(State):
    def run(self):
        print 'BurnToBody'
        self.ctrl.pitch_follow = PitchManager.ORBIT_PROGRADE
        self.ctrl.vessel.auto_pilot.engage()
        self.ctrl.vessel.auto_pilot.target_roll = 0

        last_second = datetime.now().second
        i = 0

        while True:
            i += 1
            curr_second = datetime.now().second
            if curr_second != last_second:
                print
                print 'tks:', i
                print 'alt:', self.ctrl.altitude
                print 'follow:', self.ctrl.pitch_follow
                print 'apoapsis:', self.ctrl.apoapsis_altitude
                print 'periapsis:', self.ctrl.periapsis_altitude
                print 'dv:', self.ctrl.burn_dv
                print 'bt:', self.ctrl.burn_time
                print 'bs:', self.ctrl.burn_start
                print 'ut:', self.ctrl.ut
                # print 'be:', self.burn_end_time

                i = 0
                last_second = curr_second

            if self.ctrl.ut < self.ctrl.burn_start - 4:
                self.ctrl.vessel.auto_pilot.stopping_time = (2.0, 2.0, 2.0)
            elif self.ctrl.ut < self.ctrl.burn_start - 2:
                self.ctrl.vessel.auto_pilot.stopping_time = (0.5, 0.5, 0.5)
                self.ctrl.vessel.control.rcs = False

                with self.ctrl.burn_manager.burn_end:
                    self.ctrl.burn_manager.burn_end.wait()
                    assert self.ctrl.orbit.next_orbit is not None
                    self.ctrl.set_NextStateCls(EnrouteToTarget)
                    break


class EnrouteToTarget(State):
    def run(self):
        ALTITUDE_TARGET = -self.ctrl.target_body.equatorial_radius * 0.75

        print 'EnrouteToTarget'

        self.ctrl.vessel.auto_pilot.engage()
        self.ctrl.vessel.auto_pilot.target_roll = 0

        orbit = self.ctrl.vessel.orbit.next_orbit
        periapsis_alt = self.ctrl.connection.add_stream(getattr, orbit, 'periapsis_altitude')

        # if periapsis_alt() > self.ALTITUDE_TARGET:
        if orbit.inclination < math.pi / 2.0:
            self.ctrl.pitch_follow = PitchManager.ORBIT_PROGRADE
        else:
            self.ctrl.pitch_follow = PitchManager.ORBIT_RETROGRADE
        # else:
        #     # Need to face opposite direction since we are trying to INCREASE periapsis
        #     if orbit.inclination < math.pi / 2.0:
        #         self.ctrl.pitch_follow = PitchManager.ORBIT_RETROGRADE
        #     else:
        #         self.ctrl.pitch_follow = PitchManager.ORBIT_PROGRADE

        self.ctrl.target_body = self.ctrl.space_center.bodies['Mun']

        self.ctrl.vessel.auto_pilot.wait()
        sleep(3.0)
        self.ctrl.vessel.auto_pilot.wait()
        print 'facing direction'

        TEST_DIST = 100000.0

        last_second = datetime.now().second
        i = 0

        while True:
            i += 1
            curr_second = datetime.now().second
            if curr_second != last_second:
                # orbit = self.ctrl.target_body.orbit

                print
                print 'tks:', i
                # print 'body:', self.ctrl.target_body.name
                # print 'alt:', self.ctrl.altitude
                # print 'follow:', self.ctrl.pitch_follow
                # print 'radius:', self.ctrl.target_body.equatorial_radius
                # print 'closest:', orbit.distance_at_closest_approach(self.ctrl.vessel) - self.ctrl.target_body.equatorial_radius
                # print 'periapsis:', orbit.periapsis_altitude
                # print 'eccentricity:', orbit.eccentricity
                # print 'inclination:', orbit.inclination
                # print 'dv:', self.ctrl.burn_dv
                # print 'bt:', self.ctrl.burn_time
                # print 'bs:', self.ctrl.burn_start
                # print 'ut:', self.ctrl.ut
                # print 'be:', self.burn_end_time

                i = 0
                last_second = curr_second

            periap_alt = periapsis_alt()
            if periap_alt > ALTITUDE_TARGET:
                dist_from_tgt_alt = math.fabs(periap_alt - ALTITUDE_TARGET)

                throttle_pct = dist_from_tgt_alt / TEST_DIST * 0.1 if dist_from_tgt_alt < TEST_DIST else 0.1
                if throttle_pct < 0.01:
                    throttle_pct = 0.01

                self.ctrl.vessel.control.throttle = throttle_pct
            # elif periapsis_alt() < self.ALTITUDE_TARGET * 0.75:
            #     dist_from_tgt_alt = math.fabs(periapsis_alt() - self.ALTITUDE_TARGET * 0.75)
            #
            #     throttle_pct = dist_from_tgt_alt / TEST_DIST if dist_from_tgt_alt < TEST_DIST else 1.0
            #     if throttle_pct < 0.02:
            #         throttle_pct = 0.02
            #
            #     self.ctrl.vessel.control.throttle = throttle_pct
            else:
                self.ctrl.vessel.control.throttle = 0.0

                self.ctrl.space_center.warp_to(self.ctrl.ut + self.ctrl.orbit.time_to_soi_change+5)
                # TODO: Capture burn state
                self.ctrl.set_NextStateCls(ChangeSOI)
                break

class ChangeSOI(State):
    def run(self):
        self.ctrl.space_center.warp_to(self.ctrl.ut + 90)

        self.ctrl.pitch_follow = PitchManager.ORBIT_RETROGRADE
        self.ctrl.vessel.auto_pilot.engage()
        self.ctrl.vessel.auto_pilot.wait()
        sleep(15.0)


        # conn = self.ctrl.connection
        # time_to_soi_change_call = conn.get_call(getattr, self.ctrl.orbit, 'time_to_soi_change')
        # time_to_soi_change_expr = conn.krpc.Expression.equal(
        #     conn.krpc.Expression.call(time_to_soi_change_call),
        #     conn.krpc.Expression.constant_double(float('nan')))
        # time_to_soi_change_event = conn.krpc.add_event(time_to_soi_change_expr)
        #
        # with time_to_soi_change_event.condition:
        #     self.ctrl.vessel.control.throttle = 1.0
        #     time_to_soi_change_event.wait()
        #     sleep(2.5)
        #     self.ctrl.vessel.control.throttle = 0.5
        #     sleep(2.5)
        #     self.ctrl.vessel.control.throttle = 0.0

        self.ctrl.vessel.control.throttle = 0.25
        while True:
            sleep(0.1)
            if self.ctrl.orbit.next_orbit is None:
                break

        self.ctrl.vessel.control.throttle = 0.0
        self.ctrl.set_NextStateCls(Descent)


class Descent(State):
    def run(self):
        # print 'descent...'
        from sympy import Ellipse, Circle, Point
        from sympy.geometry import intersection
        from manager import ImpactManager
        self.ctrl.impact_manager = ImpactManager()

        i = 0
        last_second = datetime.now().second

        lines = []

        ReferenceFrame = self.ctrl.space_center.ReferenceFrame

        vessel_position_stream = self.ctrl.connection.add_stream(self.ctrl.vessel.position, self.ctrl.body.reference_frame)

        surf_flight = self.ctrl.vessel.flight(self.ctrl.body.reference_frame)

        # while True:
        #     curr_second = datetime.now().second
        #
        #     if curr_second != last_second:
        #         cal_impact_time, cal_impact_pos = self.ctrl.impact_manager.impact_time_pos()
        #         # print 'imp tme: ', cal_impact_time
        #         # print 'imp pos: ', cal_impact_pos
        #         cal_impact_radius = math.sqrt(sum([val ** 2 for val in cal_impact_pos]))
        #         # print 'imp rad: ', cal_impact_radius
        #         cal_impact_pos_from_radius = self.ctrl.impact_manager.calc_pos(radius=cal_impact_radius)
        #         # print 'imp blh: ', cal_impact_pos_from_radius.x, cal_impact_pos_from_radius.y
        #         # print 'imp rad: ', cal_impact_pos_from_radius.radius
        #         # print 'imp tra: ', cal_impact_pos_from_radius.true_anomaly
        #         # print 'imp tha: ', cal_impact_pos_from_radius.theta
        #
        #         vta = self.ctrl.true_anomaly
        #         vma = self.ctrl.mean_anomaly
        #         vrad = self.ctrl.radius
        #         vessel_pos = self.ctrl.impact_manager.calc_pos(true_anomaly=vta)
        #         # vessel_radius = self.ctrl.impact_manager.calc_radius(pos=vessel_pos)
        #         aprox_dist = self.ctrl.impact_manager.approximate_distance(pos_1=cal_impact_pos_from_radius, pos_2=vessel_pos, n=100)
        #
        #         cal_time_to_impact = cal_impact_time - self.ctrl.ut
        #
        #         # mi = self.ctrl.mass
        #         # r = self.ctrl.radius
        #         # M = self.ctrl.body_mass
        #         # G = self.ctrl.G
        #         # g = (G * (M+mi) / r**2)
        #         g = self.ctrl.surface_gravity
        #         # print 'little g: ', g
        #
        #         # use mean anomaly to approximate speeds ...
        #
        #         # impact_velocity = get_speed_after_time(surf_flight.speed, cal_time_to_impact, g=g, ctrl=self.ctrl)
        #         impact_velocity = self.ctrl.impact_manager.approximate_speed(pos=cal_impact_pos_from_radius)
        #         burn_time_to_kill_imp_vel = get_burn_time_for_dv(impact_velocity, ctrl=self.ctrl)
        #
        #         suicide_burn_stop_distance = get_suicide_burn_distance(impact_velocity, g=g, ctrl=self.ctrl)
        #         suicide_burn_start_radius = cal_impact_radius + suicide_burn_stop_distance
        #         # suicide_burn_start_velocity = get_speed_after_distance(impact_velocity, -suicide_burn_stop_distance, g=g, ctrl=self.ctrl)
        #         suicide_burn_start_velocity = self.ctrl.impact_manager.approximate_speed(radius=suicide_burn_start_radius)
        #         # suicide_burn_start_radius = self.ctrl.impact_manager.calc_suicide_burn_radius(impact_velocity, cal_impact_pos_from_radius)
        #         # suicide_burn_start_radius = cal_impact_radius + suicide_burn_stop_distance
        #         # suicide_burn_burn_duration = get_suicide_burn_time(suicide_burn_start_velocity, aprox_dist, g=g, ctrl=self.ctrl)
        #
        #         print
        #         print 'tks:', i
        #         print 'dist: ', aprox_dist
        #         print 'tti: ', to_min_sec_str(cal_time_to_impact)
        #         print 'ttkv: ', burn_time_to_kill_imp_vel
        #         print 'impr: ', cal_impact_radius
        #         print 'impv: ', impact_velocity, '<---'
        #         print 'valt: ', self.ctrl.surface_altitude
        #         print 'sbsd: ', suicide_burn_stop_distance
        #         print 'sbsv: ', suicide_burn_start_velocity, '<---'
        #         print 'sbsr: ', suicide_burn_start_radius
        #         # print 'sbbd: ', to_min_sec_str(suicide_burn_burn_duration)
        #
        #         print 'spd:  {}'.format(self.ctrl.impact_manager.approximate_speed(pos=cal_impact_pos_from_radius))
        #         # print 't0: ', math.degrees(vta)
        #         # print 't1: ', math.degrees(self.ctrl.impact_manager.calc_true_anomaly(pos=vessel_pos))
        #         # print 't2: ', math.degrees(self.ctrl.impact_manager.calc_true_anomaly(radius=vrad))
        #         # # print 'm3: ', math.degrees(self.ctrl.impact_manager.calc_true_anomaly(true_anomaly=vta))
        #         # print '---'
        #         print 'm0: ', math.degrees(vma)
        #         print 'm1: ', math.degrees(self.ctrl.impact_manager.calc_mean_anomaly(pos=vessel_pos))
        #         print 'm2: ', math.degrees(self.ctrl.impact_manager.calc_mean_anomaly(radius=vrad))
        #         print 'm3: ', math.degrees(self.ctrl.impact_manager.calc_mean_anomaly(true_anomaly=vta))
        #         # print 'md: ', math.degrees(self.ctrl.impact_manager.calc_mean_anomaly(pos=vessel_pos)) - math.degrees(vma)
        #         # print 'md: ', math.degrees(self.ctrl.impact_manager.calc_mean_anomaly(pos=vessel_pos)) + math.degrees(vma)
        #         # print 'me: ', math.degrees(self.ctrl.mean_anomaly_at_epoch)
        #         # print 'ep: ', self.ctrl.epoch
        #         # print 'ut: ', self.ctrl.ut
        #         #
        #         # rots = self.ctrl.epoch / self.ctrl.rotational_period
        #         # print 'rots: ', rots
        #         # print 'mc: ', math.degrees(self.ctrl.mean_anomaly_at_epoch - (rots * 2*math.pi))
        #
        #         # print 'pos: ',  pos.x, pos.y
        #         # if mean_anomaly is None:
        #         #     mean_anomaly = self.calc_mean_anomaly(pos=pos, true_anomaly=true_anomaly, eccentric_anomaly=eccentric_anomaly)
        #         # print 'mean anom v: {}'.format(mean_anomaly)
        #         # rotational_period = self.ctrl.rotational_period
        #         # pct = mean_anomaly / (2*math.pi)
        #         # print 'mean anom p: {}'.format(pct)
        #         # t = pct * rotational_period
        #         # print self.ctrl.mean_anomaly_at_epoch
        #         # print self.ctrl.mean_anomaly
        #         # print 'mean anom t: {}'.format(t)
        #         # print 'mean anom u: {}'.format(self.ctrl.ut)
        #         # print 'mean anom e: {}'.format(self.ctrl.epoch)
        #
        #         i = 0
        #         last_second = curr_second
        #     i += 1

        self.ctrl.pitch_follow = PitchManager.SURFACE_RETROGRADE
        self.ctrl.vessel.auto_pilot.engage()
        self.ctrl.vessel.auto_pilot.target_roll = 0
        # self.ctrl.vessel.auto_pilot.stopping_time = (0.15, 0.15, 0.15)

        surf_flight = self.ctrl.vessel.flight(self.ctrl.body.reference_frame)
        cal_impact_time, cal_impact_pos = self.ctrl.impact_manager.impact_time_pos()
        cal_impact_radius = math.sqrt(sum([val ** 2 for val in cal_impact_pos]))

        cal_time_to_impact = cal_impact_time - self.ctrl.ut

        # vf = get_speed_after_time(surf_flight.speed, cal_time_to_impact, ctrl=self.ctrl)
        # vessel_pos = self.ctrl.impact_manager.calc_pos(true_anomaly=self.ctrl.true_anomaly)
        # aprox_dist = self.ctrl.impact_manager.approximate_distance(pos_1=self.ctrl.impact_manager.calc_pos(radius=cal_impact_radius), pos_2=vessel_pos, n=100)
        # suicide_burn_time = get_suicide_burn_time(vf, aprox_dist, ctrl=self.ctrl)

        impact_velocity = self.ctrl.impact_manager.approximate_speed(radius=cal_impact_radius)
        burn_time_to_kill_imp_vel = get_burn_time_for_dv(impact_velocity, ctrl=self.ctrl)

        # suicide_burn_stop_distance = get_suicide_burn_distance(impact_velocity, g=g, ctrl=self.ctrl)
        # suicide_burn_start_radius = cal_impact_radius + suicide_burn_stop_distance
        # # suicide_burn_start_velocity = get_speed_after_distance(impact_velocity, -suicide_burn_stop_distance, g=g, ctrl=self.ctrl)
        # suicide_burn_start_velocity = self.ctrl.impact_manager.approximate_speed(radius=suicide_burn_start_radius)

        print 'tti: ', cal_time_to_impact
        print 'sbt: ', burn_time_to_kill_imp_vel

        # This will always be higher then the true burn point due to using surface gravity in our vf calc
        self.ctrl.space_center.warp_to(cal_impact_time - (burn_time_to_kill_imp_vel + 45))

        sleep(5.0)
        # # self.ctrl.vessel.auto_pilot.wait(3.0)
        #
        # conn = self.ctrl.connection
        # speed_call = conn.get_call(getattr, surf_flight, 'speed')
        #
        # decent_slow_expr = conn.krpc.Expression.less_than(
        #     conn.krpc.Expression.call(speed_call),
        #     conn.krpc.Expression.constant_double(50.0))
        #
        # # Create an event from the expression
        # descent_slow_event = conn.krpc.add_event(decent_slow_expr)
        #
        # with descent_slow_event.condition:
        #     self.ctrl.set_throttle(1.0)
        #     descent_slow_event.wait()
        #     self.ctrl.set_throttle(0.0)

        self.ctrl.set_NextStateCls(SuicideBurn)


class SuicideBurn(State):
    def run(self):
        last_second = datetime.now().second
        i = 0
        cnt = 0
        sleep(2.0)

        ReferenceFrame = self.ctrl.space_center.ReferenceFrame

        # surf_flight = self.ctrl.vessel.flight(self.ctrl.body.reference_frame)

        self.ctrl.pitch_follow = PitchManager.SURFACE_RETROGRADE
        self.ctrl.vessel.auto_pilot.engage()
        self.ctrl.vessel.auto_pilot.target_roll = float('nan')
        # self.ctrl.vessel.auto_pilot.stopping_time = (0.15, 0.15, 0.15)

        # cal_time_to_impact, cal_dist, cal_impact_pos, cal_impact_ref_frame = self.ctrl.impact_manager.impact_time_pos()

        body_reference_frame = self.ctrl.body.reference_frame
        surface_velocity_reference_frame = self.ctrl.vessel.surface_velocity_reference_frame

        # ray_line = self.ctrl.connection.drawing.add_line((0, 5, 0), (0, 1, 0), surface_velocity_reference_frame)
        # ray_line.color = (0, 1.0, 0)
        #
        # ray_dist_stream = self.ctrl.connection.add_stream(
        #     self.ctrl.space_center.raycast_distance,
        #     (0, 5, 0),
        #     (0, 1, 0),
        #     surface_velocity_reference_frame)

        surf_flight = self.ctrl.vessel.flight(body_reference_frame)
        surf_speed_stream = self.ctrl.connection.add_stream(getattr, surf_flight, 'speed')
        surf_vertical_speed_stream = self.ctrl.connection.add_stream(getattr, surf_flight, 'vertical_speed')

        # rotational_period = self.ctrl.body.rotational_period

        imp_line = None

        gear = False

        conn = self.ctrl.connection

        surf_speed_call = conn.get_call(getattr, surf_flight, 'speed')
        suicide_burn_stop_expr = conn.krpc.Expression.less_than(
            conn.krpc.Expression.call(surf_speed_call),
            conn.krpc.Expression.constant_double(5.0))
        suicide_burn_stop_event = conn.krpc.add_event(suicide_burn_stop_expr)

        # legs = self.ctrl.get_parts_of_type('leg')
        # can_trust_ray = False

        while True:
            # # ray_dist = ray_dist_stream()
            # surf_flight_speed = surf_speed_stream()
            # surf_vertical_speed = surf_vertical_speed_stream()

            cal_impact_time, cal_impact_pos = self.ctrl.impact_manager.impact_time_pos()
            # cal_impact_radius = math.sqrt(sum([val ** 2 for val in cal_impact_pos]))
            cal_impact_mean_anomaly = self.ctrl.orbit.mean_anomaly_at_ut(cal_impact_time)
            # cal_impact_mean_anomaly = self.ctrl.impact_manager.calc_mean_anomaly(radius=cal_impact_radius)
            # cal_impact_pos_from_radius = self.ctrl.impact_manager.calc_pos(radius=cal_impact_radius)
            cal_impact_pos_from_time = self.ctrl.impact_manager.calc_pos(mean_anomaly=cal_impact_mean_anomaly)

            vessel_pos = self.ctrl.impact_manager.calc_pos(true_anomaly=self.ctrl.true_anomaly)
            # vessel_radius = self.ctrl.impact_manager.calc_radius(pos=vessel_pos)
            aprox_dist = self.ctrl.impact_manager.approximate_distance(pos_1=cal_impact_pos_from_time, pos_2=vessel_pos, n=100)

            # ray_time_to_impact = get_seconds_to_impact(surf_flight_speed, ray_dist, ctrl=self.ctrl)
            # if cnt % 20 == 0 and ray_time_to_impact != float('inf'):
            #     ray_impact_time = self.ctrl.ut + ray_time_to_impact
            #
            #     # body_rot = math.pi * ray_impact_time / rotational_period
            #     # ray_ref_frame = ReferenceFrame.create_relative(
            #     #     body_reference_frame, rotation=(0, math.sin(body_rot), 0, math.cos(body_rot)))
            #     ray_ref_frame = body_reference_frame
            #
            #     ray_impact_pos = self.ctrl.orbit.position_at(ray_impact_time, ray_ref_frame)
            #     # ray_aai = mun.altitude_at_position(ray_impact_pos, ray_ref_frame)
            #     # ray_lat = mun.latitude_at_position(ray_impact_pos, ray_ref_frame)
            #     # ray_lng = mun.longitude_at_position(ray_impact_pos, ray_ref_frame)
            #
            #     rel_ray_impact_pos = self.ctrl.space_center.transform_position(ray_impact_pos, ray_ref_frame, body_reference_frame)
            #     rel_ray_impact_ref_frame = ReferenceFrame.create_relative(body_reference_frame, position=rel_ray_impact_pos)
            #     rel_ray_vessel_pos = self.ctrl.vessel.position(rel_ray_impact_ref_frame)
            #
            #     if imp_line is not None:
            #         imp_line.remove()
            #     imp_line = self.ctrl.connection.drawing.add_line((0, 0, 0), rel_ray_vessel_pos, rel_ray_impact_ref_frame)
            #     imp_line.color = (0, 0, 1)

            # if ray_time_to_impact > 0:
            #     time_to_impact = ray_time_to_impact
            # else:
            #     time_to_impact = cal_time_to_impact

            # dist_pct_diff = ray_dist / cal_dist
            # if ray_dist != float('inf') and ray_dist > 0 and 0.5 < dist_pct_diff < 1.5:
            #     dist = ray_dist
            #     can_trust_ray = True
            # else:
            #     dist = cal_dist
            #     can_trust_ray = False
            #
            # # vf = get_speed_after_time(surf_flight.speed, time_to_impact)
            # # impact_plus_1km = get_time_for_distance(surf_flight.speed, 1000)
            # # use that speed to make the suicide burn happen 100m higher
            #
            # thrust = get_avail_thrust(vessel)
            # a = thrust - active_body.surface_gravity

            # suicide_burn_time = get_suicide_burn_time(surf_flight.speed, dist, use_local_g=True)
            # suicide_burn_start_time = ut + time_to_impact - suicide_burn_time #- impact_plus_1km
            # suicide_burn_start_alt = get_suicide_burn_alt(surf_flight.speed, use_local_g=True, ctrl=self.ctrl)

            # cal_time_to_impact = cal_impact_time - self.ctrl.ut
            # impact_velocity = get_speed_after_time(surf_flight_speed, cal_time_to_impact, ctrl=self.ctrl)
            #
            # suicide_burn_start_distance = get_suicide_burn_distance(impact_velocity, ctrl=self.ctrl)
            # suicide_burn_start_speed = get_speed_after_distance(impact_velocity, -suicide_burn_start_distance, ctrl=self.ctrl)
            # # suicide_burn_start_radius = self.ctrl.impact_manager.calc_suicide_burn_radius(impact_velocity, cal_impact_pos_from_radius)
            # suicide_burn_start_radius = cal_impact_radius + suicide_burn_start_distance
            # suicide_burn_start_time = get_suicide_burn_time(surf_flight_speed, aprox_dist, ctrl=self.ctrl)


            # *****
            mi = self.ctrl.mass
            r = self.ctrl.radius
            M = self.ctrl.body_mass
            G = self.ctrl.G
            g = (G * (M+mi) / r**2)
            # g = None

            # impact_velocity = get_speed_after_time(surf_flight.speed, cal_time_to_impact, g=g, ctrl=self.ctrl)
            impact_velocity = self.ctrl.impact_manager.approximate_speed(pos=cal_impact_pos_from_time)
            burn_time_to_kill_imp_vel = get_burn_time_for_dv(impact_velocity, g=g, ctrl=self.ctrl)

            suicide_burn_stop_distance = get_suicide_burn_distance(impact_velocity, g=g, ctrl=self.ctrl)
            # suicide_burn_start_radius = cal_impact_radius + suicide_burn_stop_distance
            # suicide_burn_start_velocity = get_speed_after_distance(impact_velocity, -suicide_burn_stop_distance, g=g, ctrl=self.ctrl)

            burn_time_to_stop = self.ctrl.impact_manager.calc_time_for_speed_dist(impact_velocity, 0, suicide_burn_stop_distance)
            offset = 0 #burn_time_to_kill_imp_vel * 0.1
            burn_start_mean_anomaly = self.ctrl.impact_manager.calc_mean_anomaly(pos=cal_impact_pos_from_time, time_offset=-burn_time_to_kill_imp_vel+offset)
            burn_start_mean_anomaly_minus_10 = self.ctrl.impact_manager.calc_mean_anomaly(pos=cal_impact_pos_from_time, time_offset=-burn_time_to_kill_imp_vel-10+offset)

            suicide_burn_start_velocity = self.ctrl.impact_manager.approximate_speed(mean_anomaly=burn_start_mean_anomaly)

            # suicide_burn_start_radius = self.ctrl.impact_manager.calc_suicide_burn_radius(impact_velocity, cal_impact_pos_from_radius)
            # suicide_burn_start_radius = cal_impact_radius + suicide_burn_stop_distance
            # suicide_burn_burn_duration = get_suicide_burn_time(suicide_burn_start_velocity, aprox_dist, g=g, ctrl=self.ctrl)
            # *****

            i += 1
            cnt += 1
            curr_second = datetime.now().second

            if curr_second != last_second:
                # orbit = self.ctrl.target_body.orbit

                # if ray_dist != float('inf') and ray_dist > 0 and 0.5 < dist_pct_diff < 1.5:
                #     pass
                # else:
                #     cal_time_to_impact, cal_dist, cal_impact_pos, cal_impact_ref_frame = find_true_impact_time(self.ctrl.vessel, ctrl=self.ctrl)

                # we need to get the m/s at the time of the start of the suicide burn
                # vf = get_speed_after_time(surf_flight_speed, time_to_impact, ctrl=self.ctrl)
                # impact_plus_1km = get_time_for_distance(vf, 1000)
                # use that speed to make the suicide burn happen 100m higher

                # mi = self.ctrl.mass
                # r = self.ctrl.radius
                # M = self.ctrl.body_mass
                # G = self.ctrl.G
                #
                # g = (G * (M + mi) / r ** 2)
                # thrust = self.ctrl.available_thrust
                # accel = thrust / mi - g

                print
                print 'tks:', i
                # print 'mi:', mi
                # print 'r: ', r
                # print 'M: ', M
                # print 'G: ', G
                # print 'g: ', g
                # print 't: ', thrust
                # print 'accl: ', accel
                # print 'sp:', surf_flight.speed
                # print 'bt:', suicide_burn_time
                # print 'ut:', ut, 'bs:', suicide_burn_start_time
                # print 'ba:', suicide_burn_start_alt, 'dist:', dist
                # print 'ssp: ', surf_flight_speed
                # print 'vsp: ', surf_vertical_speed
                # print 'sad: ', get_speed_after_distance(surf_flight_speed, aprox_dist, ctrl=self.ctrl)
                # print 'rimp: ', to_min_sec_str(ray_time_to_impact if ray_time_to_impact != float('inf') else -1)
                # print 'impt: ', to_min_sec_str(cal_impact_time)
                print 'cimp: ', to_min_sec_str(cal_impact_time - self.ctrl.ut)
                # print 'time: ', self.ctrl.impact_manager.calc_time(mean_anomaly=cal_impact_mean_anomaly) - self.ctrl.ut
                print 'time: ', to_min_sec_str(self.ctrl.impact_manager.calc_time(mean_anomaly=cal_impact_mean_anomaly) - self.ctrl.ut)
                print 'bs_1: ', to_min_sec_str(self.ctrl.impact_manager.calc_time(mean_anomaly=burn_start_mean_anomaly) - self.ctrl.ut)
                print 'bs10: ', to_min_sec_str(self.ctrl.impact_manager.calc_time(mean_anomaly=burn_start_mean_anomaly_minus_10) - self.ctrl.ut)
                # print '1km: ', impact_plus_1km
                # print 'rdst: ', ray_dist
                print 'cdst: ', aprox_dist
                print 'sbsd: ', suicide_burn_stop_distance
                print 'btki: ', burn_time_to_kill_imp_vel
                print 'btts: ', burn_time_to_stop
                # print 'diff: ', dist_pct_diff
                print 'impv: ', impact_velocity
                print 'srtv: ', suicide_burn_start_velocity
                print 'vspd:', self.ctrl.vertical_speed
                # print 'vsma: ', self.ctrl.mean_anomaly
                # print 'bsma: ', burn_start_mean_anomaly
                # print 'ipma: ', cal_impact_mean_anomaly
                # # print 'ialt: ', self.ctrl.orbit.alti(cal_impact_time)
                # print 'irad: ', self.ctrl.impact_manager.calc_radius(mean_anomaly=cal_impact_mean_anomaly)
                # print 'sbt: ', to_min_sec_str(suicide_burn_start_time)
                # print 'sbd: ', suicide_burn_start_distance
                # print 'sbr: ', suicide_burn_start_radius
                # print 'sbs: ', suicide_burn_start_speed

                # suicide_burn_time = get_suicide_burn_time(vf, cal_dist)
                # suicide_burn_start_time = ut + cal_time_to_impact - suicide_burn_time - impact_plus_1km
                # suicide_burn_start_alt = get_suicide_burn_alt(vf, cal_dist)

                # set_state(SUICIDE_BURN)

                # # body_impact_pos = self.ctrl.space_center.transform_position(cal_impact_pos, ray_ref_frame, body_reference_frame)
                # body_vessel_pos = self.ctrl.space_center.transform_position((0, 0, 0), self.ctrl.vessel.reference_frame, self.ctrl.body.reference_frame)
                # imp_line = self.ctrl.connection.drawing.add_line(body_vessel_pos, cal_impact_pos, self.ctrl.body.reference_frame)
                # imp_line.color = (0, 0, 1)

                i = 0
                last_second = curr_second

            if self.ctrl.mean_anomaly > burn_start_mean_anomaly_minus_10:
                if not gear:
                    self.ctrl.vessel.control.gear = True

                # if can_trust_ray:
                #     error = (suicide_burn_start_alt + 15 - ray_dist_stream())
                # else:
                # error = (suicide_burn_start_alt + 15 - aprox_dist)
                #
                # if 0.0 < error < 5000.0:
                # if can_trust_ray:
                #     print 'YES TRUST RAY'
                #     dict_call = conn.get_call(
                #         self.ctrl.space_center.raycast_distance,
                #         (0, 5, 0),
                #         (0, 1, 0),
                #         surface_velocity_reference_frame)
                #
                #     suicide_burn_start_expr = conn.krpc.Expression.less_than(
                #         conn.krpc.Expression.call(dict_call),
                #         conn.krpc.Expression.constant_double(suicide_burn_start_alt + error))
                #     suicide_burn_start_event = conn.krpc.add_event(suicide_burn_start_expr)
                # else:
                # print 'NO TRUST RAY'
                # E = conn.krpc.Expression
                #
                # orbit = self.ctrl.orbit
                # ref_frame = self.ctrl.body.reference_frame

                # ut_call = conn.get_call(getattr, self.ctrl.space_center, 'ut')
                # e_tti = E.constant_double(cal_time_to_impact)
                #
                # position_arg_names = E.create_list([E.constant_string('ut'), E.constant_string('reference_frame')])
                #
                # vessel_pos_call = E.call(orbit.position_at, E.call(ut_call), ref_frame)
                # vessel_pos_list = E.call(vessel_pos_call)
                #
                # # vessel_arg_vals = E.create_list([ut_call, ref_frame])
                # # vessel_arg_dict = E.create_dictionary(position_arg_names, vessel_arg_vals)
                # # vessel_pos_list = E.to_list(E.invoke(orbit.position_at, vessel_arg_dict))
                #
                # impact_arg_vals = E.create_list([E.sum(ut_call, e_tti), ref_frame])
                # impact_arg_dict = E.create_dictionary(position_arg_names, impact_arg_vals)
                # impact_pos_list = E.to_list(E.invoke(orbit.position_at, impact_arg_dict))
                #
                # v_x = E.get(vessel_pos_list, E.constant_double(0))
                # v_y = E.get(vessel_pos_list, E.constant_double(1))
                # v_z = E.get(vessel_pos_list, E.constant_double(2))
                #
                # i_x = E.get(impact_pos_list, E.constant_double(0))
                # i_y = E.get(impact_pos_list, E.constant_double(1))
                # i_z = E.get(impact_pos_list, E.constant_double(2))
                #
                # p_x = E.power(E.subtract(v_x, i_x), E.constant_double(2))
                # p_y = E.power(E.subtract(v_y, i_y), E.constant_double(2))
                # p_z = E.power(E.subtract(v_z, i_z), E.constant_double(2))
                #
                # p_list = E.create_list(p_x, p_y, p_z)
                # p_sum = E.sum(p_list)
                # dist_pow_2 = E.power(E.constant_double(dist), E.constant_double(2))
                #
                # E.less_than(p_sum, dist_pow_2)
                #
                # suicide_burn_start_expr = E.less_than(p_sum, dist_pow_2)
                # suicide_burn_start_event = conn.krpc.add_event(suicide_burn_start_expr)

                # This will need to change for direction of travel i believe? depends on how mean anomaly is reported
                print 'building condition for landing'
                orbit_mean_anomaly_call = conn.get_call(getattr, self.ctrl.orbit, 'mean_anomaly')
                suicide_burn_start_expr = conn.krpc.Expression.greater_than(
                    conn.krpc.Expression.call(orbit_mean_anomaly_call),
                    conn.krpc.Expression.constant_double(burn_start_mean_anomaly))
                suicide_burn_start_event = conn.krpc.add_event(suicide_burn_start_expr)

                with suicide_burn_start_event.condition:
                    print 'waiting: {} {}'.format(self.ctrl.mean_anomaly, burn_start_mean_anomaly)
                    suicide_burn_start_event.wait()
                    self.ctrl.vessel.control.throttle = 1.0

                with suicide_burn_stop_event.condition:
                    suicide_burn_stop_event.wait(burn_time_to_kill_imp_vel + 5)
                    # self.ctrl.vessel.control.throttle = 0.0

                    # self.ctrl.vessel.control.throttle = 3.0 / self.ctrl.get_avail_twr()
                    # sleep(1.0)

                while True:
                    vert_speed = self.ctrl.vertical_speed #surf_vertical_speed_stream()

                    # ves_pos = self.ctrl.impact_manager.calc_pos(true_anomaly=self.ctrl.true_anomaly)
                    # imp_pos = self.ctrl.impact_manager.calc_pos(mean_anomaly=cal_impact_mean_anomaly)
                    # # vessel_radius = self.ctrl.impact_manager.calc_radius(pos=vessel_pos)
                    # # aprox_dist = self.ctrl.impact_manager.approximate_distance(mean_anoamly=imp_pos, pos_2=ves_pos, n=100)
                    # print 'dist: ', ves_pos.distance(imp_pos)

                    # print 'sit: ', self.ctrl.vessel.situation, '|', vert_speed
                    if self.ctrl.vessel.situation == self.ctrl.space_center.VesselSituation.landed:
                        break

                    if vert_speed < -10.0:
                        self.ctrl.pitch_follow = PitchManager.SURFACE_RETROGRADE
                        self.ctrl.vessel.control.throttle = 1.0
                    elif self.ctrl.surface_altitude > 50.0:
                        self.ctrl.pitch_follow = PitchManager.SURFACE_RETROGRADE
                        if vert_speed < -5.0:
                            self.ctrl.vessel.control.throttle = 1.0 / self.ctrl.get_avail_twr()
                        else:
                            self.ctrl.vessel.control.throttle = 0.35 / self.ctrl.get_avail_twr()
                    else:
                        if vert_speed < -5.0:
                            self.ctrl.vessel.control.throttle = 10.0 / self.ctrl.get_avail_twr()
                        else:
                            self.ctrl.pitch_follow = PitchManager.FIXED_UP

                            if vert_speed < -2.5:
                                self.ctrl.vessel.control.throttle = 3.0 / self.ctrl.get_avail_twr()
                            elif vert_speed < -1.0:
                                self.ctrl.vessel.control.throttle = 1.0 / self.ctrl.get_avail_twr()
                            else:
                                self.ctrl.vessel.control.throttle = 0.75 / self.ctrl.get_avail_twr()

                # self.ctrl.vessel.control.throttle = 0.50 / self.ctrl.get_avail_twr()
                # print 'pre landed'
                # while True:
                #     for part in legs:
                #         if part.leg.is_grounded:
                #             break
                #     sleep(0.05)

                print 'landed'
                self.ctrl.vessel.control.throttle = 0.0
                sleep(5.0)
                self.ctrl.vessel.auto_pilot.disengage()
                self.ctrl.vessel.auto_pilot.sas = True
                break

                # if dist < suicide_burn_start_alt:
                #     if surf_vertical_speed < -5.0:
                #         if suicide_burn_start_alt - dist > 0.5:
                #             self.ctrl.set_throttle(1.0)
                #         else:
                #             self.ctrl.set_throttle(0.705)
                #     else:
                #         avail_twr = self.ctrl.get_avail_twr()
                #         self.ctrl.set_throttle(0.85 / avail_twr)
                #         self.ctrl.pitch_follow = PitchManager.FIXED_UP
                #         break
                #         # set_state(LAND)


class TransitionToHover(State):
    def run(self):
        # self.ctrl.pitch_follow = PitchManager.FIXED_UP
        self.ctrl.pitch_follow = PitchManager.CUSTOM_PITCH_HEADING
        pitch, heading = get_vessel_pitch_heading(self.ctrl.vessel)
        self.ctrl.pitch_manager.custom_pitch_heading = (0, heading)

        vessel = self.ctrl.vessel

        vessel.auto_pilot.engage()
        vessel.auto_pilot.target_roll = 0

        last_second = datetime.now().second

        i = 0
        while True:
            i += 1
            curr_second = datetime.now().second
            if curr_second != last_second:
                print
                print 'tks:', i
                print 'stms:', self.ctrl._streams_open
                print 'alt:', self.ctrl.altitude
                print 'speed:', self.ctrl.vertical_speed
                print 'follow:', self.ctrl.pitch_follow
                print 'apoapsis:', self.ctrl.apoapsis_altitude
                print 'periapsis:', self.ctrl.periapsis_altitude

                i = 0
                last_second = curr_second

            if self.ctrl.apoapsis_altitude <= SurfaceHover.MIN_HEIGHT:
                # target_twr = 1.1
                # avail_twr = get_avail_twr(self.ctrl)
                # throttle_pct = target_twr / avail_twr
                self.ctrl.set_throttle(1.0)
            else:
                self.ctrl.set_throttle(0.0)

            if self.ctrl.surface_altitude > SurfaceHover.MIN_HEIGHT:
                self.ctrl.set_NextStateCls(SurfaceHover)
                break


class SurfaceHover(State):
    MIN_HEIGHT = 15.0
    MAX_HEIGHT = 20.0
    SPEED = 0.15

    def run(self):
        self.ctrl.pitch_follow = PitchManager.FIXED_UP
        self.ctrl.throttle_manager.avg_input = True

        vessel = self.ctrl.vessel

        vessel.auto_pilot.engage()
        # vessel.auto_pilot.target_roll = 0

        # conn = krpc.connect(name='User Interface Example')
        canvas = self.ctrl.connection.ui.stock_canvas

        # Get the size of the game window in pixels
        screen_size = canvas.rect_transform.size

        # Add a panel to contain the UI elements
        panel = canvas.add_panel()

        # Position the panel on the left of the screen
        rect = panel.rect_transform
        rect.size = (200, 100)
        rect.position = (110 - (screen_size[0] / 2), 0)

        # Add a button to set the throttle to maximum
        fwd_btn = panel.add_button("Forward")
        fwd_btn.rect_transform.position = (0, 30)
        hvr_btn = panel.add_button("Hover")
        hvr_btn.rect_transform.position = (0, 0)
        rvs_btn = panel.add_button("Reverse")
        rvs_btn.rect_transform.position = (0, -30)

        # Set up a stream to monitor the throttle button
        fwd_btn_clicked = self.ctrl.connection.add_stream(getattr, fwd_btn, 'clicked')
        hvr_btn_clicked = self.ctrl.connection.add_stream(getattr, hvr_btn, 'clicked')
        rvs_btn_clicked = self.ctrl.connection.add_stream(getattr, rvs_btn, 'clicked')

        last_second = datetime.now().second
        i = 0
        while True:
            i += 1
            curr_second = datetime.now().second

            pitch, heading = get_vessel_pitch_heading(self.ctrl.vessel)

            if curr_second != last_second:
                print
                print 'tks:', i
                print 'stms:', self.ctrl._streams_open
                print 'alt:', self.ctrl.altitude
                print 'speed:', self.ctrl.vertical_speed
                print 'follow:', self.ctrl.pitch_follow
                print 'ptch_head:', self.ctrl.pitch_manager.custom_pitch_heading
                print 'pitch:', pitch
                print 'heading:', heading
                print 'apoapsis:', self.ctrl.apoapsis_altitude
                print 'periapsis:', self.ctrl.periapsis_altitude
                print

                i = 0
                last_second = curr_second

            # Handle the throttle button being clicked
            # print fwd_btn_clicked(), '|', hvr_btn_clicked(), '|', rvs_btn_clicked()
            if fwd_btn_clicked():
                self.pitch_follow = PitchManager.CUSTOM_PITCH_HEADING
                # flight = self.vessel.flight(self.vessel.surface_velocity_reference_frame)
                pitch, heading = get_vessel_pitch_heading(self.ctrl.vessel)
                self.ctrl.pitch_manager.custom_pitch_heading = (-60, heading)
                fwd_btn.clicked = False
            elif hvr_btn_clicked():
                self.pitch_follow = PitchManager.CUSTOM_PITCH_HEADING
                pitch, heading = get_vessel_pitch_heading(self.ctrl.vessel)
                self.ctrl.pitch_manager.custom_pitch_heading = (0, heading)
                hvr_btn.clicked = False
            elif rvs_btn_clicked():
                self.pitch_follow = PitchManager.CUSTOM_PITCH_HEADING
                pitch, heading = get_vessel_pitch_heading(self.ctrl.vessel)
                self.ctrl.pitch_manager.custom_pitch_heading = (60, heading)
                rvs_btn.clicked = False

            avail_twr = get_avail_twr(self.ctrl)
            surf_apoapsis_alt = self.ctrl.surface_altitude + self.ctrl.apoapsis_altitude
            if surf_apoapsis_alt <= self.MIN_HEIGHT:
                if self.ctrl.vertical_speed < 0:
                    target_twr = avail_twr
                else:
                    target_twr = 1.25
            elif self.MIN_HEIGHT < surf_apoapsis_alt < self.MAX_HEIGHT:
                if self.ctrl.vertical_speed <= -self.SPEED:
                    target_twr = 1.75
                elif -self.SPEED < self.ctrl.vertical_speed < self.SPEED:
                    spread = (self.MAX_HEIGHT - self.MIN_HEIGHT) / 2.0
                    mid_alt = self.MIN_HEIGHT + spread
                    alt_diff = mid_alt - surf_apoapsis_alt

                    target_twr = 1.0 + (alt_diff / spread) * 0.5
                else:
                    target_twr = 0.25

            else:
                # if self.ctrl.vertical_speed < 0:
                #     target_twr = 1.25
                # else:
                target_twr = 0.5

            throttle_pct = target_twr / avail_twr
            self.ctrl.set_throttle(throttle_pct)
