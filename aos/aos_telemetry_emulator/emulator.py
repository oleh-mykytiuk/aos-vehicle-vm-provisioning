from collections import namedtuple, deque
import random
import math
import json
import sys
import os

Vertex = namedtuple('Vertex', ['id', 'x', 'y', 'neighbors'])
# neighbors - list of id
Point = namedtuple('Point', ['longitude', 'latitude'])


class VertexPool:
    RAD = 0.000008998719243599958

    def __init__(self, filename):
        self._load_from_file(filename)

    def lat_to_meters(self, lat):
        return (lat - self.min_lat) / self.RAD

    def lon_to_meters(self, lon):
        return (lon - self.min_lon) / self.RAD

    def y_to_lat(self, y):
        return y * self.RAD + self.min_lat

    def x_to_lon(self, x):
        return x * self.RAD + self.min_lon

    def _load_from_file(self, filename):
        data = json.load(open(filename, 'r'))
        self.min_lat = data['min_latitude']
        self.min_lon = data['min_longitude']

        self.vertices = [Vertex(v['id'], v['x'], v['y'], v['neighbours']) for v in data['vertices']]

    def __len__(self):
        return len(self.vertices)

    def __getitem__(self, item):
        return self.vertices[item]


Position = namedtuple('Position', ['x', 'y'])


class PlanPoint:
    def __init__(self, vertex, turn_angle, max_turn_speed, distance_from_current_point):
        self.vertex = vertex
        self.turn_angle = turn_angle
        self.max_turn_speed = max_turn_speed
        self.distance_from_current_point = distance_from_current_point


def distance(start: Position, end: Position):
    return math.sqrt((end.x - start.x) ** 2 + (end.y - start.y) ** 2)


def calc_angle(prev, cur, next):
    turn_angle = math.atan2(cur.y - prev.y, cur.x - prev.x) - math.atan2(next.y - cur.y, next.x - cur.x)
    if turn_angle > math.pi:
        turn_angle -= 2 * math.pi
    if turn_angle < -math.pi:
        turn_angle += 2 * math.pi
    return turn_angle


def gauss_distribution_density(x, mu, sigma):
    return 1 / (sigma * math.sqrt(2 * math.pi)) * math.exp(-(x - mu) ** 2 / (2 * sigma ** 2))


def calc_turn_angle(x, sigma):
    return gauss_distribution_density(x * 2, 0, sigma) / gauss_distribution_density(0, 0, sigma)


class RandomShift:
    def __init__(self, min_shift, max_shift, speed=None, is_updating_from_file=False):
        self.min_shift = min_shift
        self.max_shift = max_shift
        self.shift = 0
        self._gauss_factor = ((max_shift - min_shift) / 2) / 3  # half size dived by 3 sigma
        self.wrapped_function = None
        self.speed = speed or (max_shift - min_shift) / 2 * 0.01
        self._update_desired_shift()
        self._is_updating_from_file = is_updating_from_file
        self._last_file_data = None

    def __call__(self, wrapped_function):
        self.wrapped_function = wrapped_function
        return self

    def __get__(self, instance, owner):
        self._update()
        new_val = self._update_from_file()

        if new_val is not None:
            self.shift = new_val

        return self.wrapped_function(instance) + self.shift

    def _update(self):
        if math.isclose(self.shift, self._desired_shift):
            self._update_desired_shift()
        sign = math.copysign(1, self._desired_shift - self.shift)
        self.shift += sign * min(abs(self._desired_shift - self.shift), self.speed)

    def _update_desired_shift(self):
        self._desired_shift = random.gauss(0, 1) * self._gauss_factor

    def _update_from_file(self):
        if not self._is_updating_from_file:
            return None

        try:
            file = open(os.path.join(os.path.dirname(__file__), 'emulator_params', self.wrapped_function.__name__), "r")
            new_val = int(file.read())
            if new_val != self._last_file_data:
                self._last_file_data = new_val
                return self._last_file_data
        except (FileNotFoundError, ValueError):
            return None


class TurnSignal:
    DISABLED = 0
    LEFT = 1
    RIGHT = 2
    EMERGENCY = 3


class Emulator:
    KMPH_TO_MPS = 0.277777777777
    MPS_TO_KMPH = 1 / KMPH_TO_MPS

    MAX_SPEED = 25  # meters per second ~ 90 kmph
    MIN_SPEED = 2.77777710  # meters per second ~ 10 kmph
    MAX_TURN_AROUND_SPEED = MIN_SPEED  # Must be equals or greater than MIN_SPEED
    MAX_ACCELERATION = 2.77777  # meters per second
    MIN_ACCELERATION = 0.5
    MAX_BREAK = 4
    MIN_BREAK = 1
    INITIAL_SPEED = 0
    PLAN_LENGTH = 10  # minimum 3 for previous, current and next points

    MADNESS_CHANGE_TICKS = 400  # ticks till driver madness changes
    ACCELERATION_TO_FUEL_CONSUMPTION_RATIO = 2.59  # acceleration * ACCELERATION_TO_FUEL_CONSUMPTION_RATIO (l/100km)
    MIN_FUEL_CONSUMPTION = 4  # liters per 100km
    LINE_WIDTH = 1.5
    LINE_CHANGE_CHANCE = 0.01

    STOP_SIGNAL_BREAK_THRESHOLD = 0.5
    TURN_SIGNAL_TICKS = 8
    TURN_SIGNAL_ANGLE_THRESHOLD = 0.8726646259971648  # 50 degrees
    TURN_SIGNAL_DISTANCE = 20
    TURN_STEERING_WHEEL_DISTANCE = 10
    FUEL_CONSUMPTION = 17  # litres / 100 km
    FUEL_TANK_SIZE = 100  # litres

    MIN_RPM = 800
    SPEED_TO_TURN_GEAR = 5.1
    REPLACE_TIRE_COUNTDOWN = 236

    def __init__(self, vertex_pool: VertexPool):
        self._tick = 0
        self._rectangle_to = False
        self._rectangle = None
        self._rectangle_plan = {}
        self._vertex_pool = vertex_pool
        self._acceleration = 0
        self._turn_angle = 0
        self._speed = self.INITIAL_SPEED
        self._max_speed = self.MAX_SPEED
        self._max_break = self.MAX_BREAK
        self._max_acceleration = self.MAX_ACCELERATION
        self._madness = 0.5
        self._plan = deque()
        self._turn_signal_countdown = 0
        self._turn_signal = TurnSignal.DISABLED
        self.madness = 0.7
        self.change_madness_periodically = True
        self._ticks_till_next_madness = self.MADNESS_CHANGE_TICKS
        self._line_offset = 0  # negative means offset to left from center
        self._command_to_stop = False
        self._init_plan()
        self._x = self._prev.x
        self._y = self._prev.y
        self._odometer = 232000
        self._gas_range = 423000
        self.tire_pressure = 27
        self._broken_tire = False
        self._replace_tire_countdown = self.REPLACE_TIRE_COUNTDOWN

        self._angle = math.atan2(self._current.y - self._prev.y, self._current.x - self._prev.x)
        self._distance_till_turn = distance(self._prev, self._current)
        self.drv_ajar = False
        self.drv_seatbelt = 0
        self.rr_dr_unlkd = False

    def set_rectangle_direction(self, target: bool):
        target = bool(target)
        if self._rectangle_to != target:
            self._rectangle_to = target
            self._rectangle_plan = {}

    def set_rectangle(self, long0, lat0, long1, lat1):
        new_rectangle = Point(long0, lat0), Point(long1, lat1)
        if new_rectangle != self._rectangle:
            self._rectangle = new_rectangle
            self._rectangle_plan = {}

    def del_rectangle(self):
        self._rectangle = None
        self._rectangle_plan = {}

    def _init_plan(self):
        self._plan = deque()

        # prev
        prev_vertex = random.choice(self._vertex_pool)
        self._plan.append(PlanPoint(prev_vertex, 0, 0, 0))

        # cur
        cur_vertex = self._get_random_next_vertex(self._plan[0].vertex)
        self._plan.append(PlanPoint(cur_vertex, 0, 0, 0))

        for _ in range(self.PLAN_LENGTH - 2):
            self._add_point_to_plan()

    def _in_rectangle(self, vertex: Vertex = None) -> bool:
        result = False
        if self._rectangle:
            if vertex:
                longitude = self._vertex_pool.x_to_lon(vertex.x)
                latitude = self._vertex_pool.y_to_lat(vertex.y)
            else:
                longitude = self.lon
                latitude = self.lat

            top_left, bottom_right = self._rectangle

            in_longitude = longitude > min(top_left.longitude, bottom_right.longitude) \
                           and longitude < max(top_left.longitude, bottom_right.longitude)
            in_latitude = latitude > min(top_left.latitude, bottom_right.latitude) and \
                          latitude < max(top_left.latitude, bottom_right.latitude)

            result = in_longitude and in_latitude

        return result

    def _create_rectangle_movement_plan(self):
        rectangle_plan = {}
        target_vertex = None
        visited = {self._plan[-2].vertex.id: None}
        next_ids = {self._plan[-1].vertex.id: self._plan[-2].vertex.id}

        if self._in_rectangle(vertex=self._plan[-1].vertex) ^ self._rectangle_to:
            while target_vertex is None and next_ids:
                new_next_ids = {}
                for vertex_id, came_from_id in next_ids.items():
                    if vertex_id in visited:
                        continue
                    visited[vertex_id] = came_from_id
                    vertex = self._vertex_pool[vertex_id]
                    if (not self._in_rectangle(vertex=vertex)) ^ self._rectangle_to:
                        target_vertex = vertex
                        break

                    # update neighbours vertices
                    new_next_ids.update({vid: vertex_id for vid in vertex.neighbors})

                next_ids = new_next_ids

            if target_vertex is not None:
                current_id = target_vertex.id
                previous_id = visited[current_id]
                while previous_id is not None:
                    rectangle_plan[previous_id] = current_id
                    current_id = previous_id
                    previous_id = visited[current_id]

        self._rectangle_plan = rectangle_plan

    def _add_point_to_plan(self):
        prev = self._plan[-2]
        cur = self._plan[-1]

        next_vertex = None
        if self._rectangle and (self._in_rectangle(vertex=cur.vertex) ^ self._rectangle_to):
            if not self._rectangle_plan:
                self._create_rectangle_movement_plan()
            if cur.vertex.id in self._rectangle_plan:
                next_vertex_id = self._rectangle_plan.pop(cur.vertex.id)
                next_vertex = self._vertex_pool[next_vertex_id]
                print(">>", next_vertex, "<<", self._rectangle_plan)
                if next_vertex_id not in self._rectangle_plan:
                    self._rectangle_plan = {}

        if next_vertex is None:
            next_vertex = self._get_random_next_vertex(self._plan[-1].vertex, self._plan[-2].vertex)

        cur.turn_angle = calc_angle(prev.vertex, cur.vertex, next_vertex)
        cur.max_turn_speed = self._calc_max_turn_speed(cur.turn_angle)

        distance_from_current_point = cur.distance_from_current_point + distance(cur.vertex, next_vertex)
        self._plan.append(PlanPoint(next_vertex, 0, 0, distance_from_current_point))

    def _get_random_next_vertex(self, current, prev=None):
        possible_next_ids = list(current.neighbors)
        if prev and len(possible_next_ids) >= 2 and prev.id in possible_next_ids:
            possible_next_ids.remove(prev.id)
        next_id = random.choice(possible_next_ids)
        return self._vertex_pool[next_id]

    def _calc_max_turn_speed(self, turn_angle):
        max_speed_for_curr_turn_angle = (self.MAX_SPEED - self.MAX_TURN_AROUND_SPEED) * (1 - abs(turn_angle) / math.pi)
        max_turn_speed = self.MIN_SPEED + (max_speed_for_curr_turn_angle - self.MIN_SPEED) * self.madness
        return max_turn_speed

    def update(self, time_delta=1.0):
        assert time_delta > 0
        self._tick += 1
        self._check_turn_signal_to_disable()
        self._update_madness_if_needed()

        if self._broken_tire:
            self._update_broken_tire(time_delta)
        if self._command_to_stop:
            self._enable_turn_signal(TurnSignal.EMERGENCY)
            self._break(time_delta, emergency=True)
        elif self._want_to_break(time_delta):
            self._break(time_delta)
            self._show_turn_signal_if_needed()
        else:
            self._accelerate(time_delta)
            self._show_turn_signal_if_needed()

        if self._is_time_to_turn(time_delta):
            self._turn_and_move(time_delta)
        elif self._distance_till_turn < self.TURN_STEERING_WHEEL_DISTANCE:
            self._turn_angle = calc_turn_angle(self._distance_till_turn,
                                               self.TURN_STEERING_WHEEL_DISTANCE) * self._current_turn_angle
            self._move(self._speed, time_delta)
        else:
            self._change_line(time_delta)
            self._move(self._speed, time_delta)

        self._distance_till_turn = distance(Position(self._x, self._y), self._current)

    def _check_turn_signal_to_disable(self):
        if self._turn_signal_countdown:
            self._turn_signal_countdown -= 1
            if self._turn_signal_countdown == 0:
                self._turn_signal = TurnSignal.DISABLED

    def _update_broken_tire(self, time_delta):
        self._replace_tire_countdown -= 1

        if self._replace_tire_countdown >= 180:
            self.tire_pressure -= (27 - 14) / (236 - 180)  # pressure must fall from 27 to 14 during 236 - 180 interval

        if self._replace_tire_countdown == 215:
            self._command_to_stop = True

        if self._replace_tire_countdown == 190:  # hope that it stopped till this countdown
            self.drv_ajar = True
            self.drv_seatbelt = 1

        if self._replace_tire_countdown == 180:
            self.drv_ajar = False

        if self._replace_tire_countdown == 165:
            self.rr_dr_unlkd = True

        if 74 <= self._replace_tire_countdown <= 100:
            # pressure must increase from 14 to 27 during 100 - 74 interval
            self.tire_pressure += min((27 - 14) / (100 - 74), 27 - self.tire_pressure)

        if self._replace_tire_countdown == 35:
            self.rr_dr_unlkd = False

        if self._replace_tire_countdown == 20:
            self.drv_ajar = True

        if self._replace_tire_countdown == 10:
            self.drv_ajar = False
            self.drv_seatbelt = 0

        if self._replace_tire_countdown == 0:
            self._command_to_stop = False
            self._replace_tire_countdown = self.REPLACE_TIRE_COUNTDOWN
            self._broken_tire = False
            self.tire_pressure = 27

    def _want_to_break(self, time_delta):
        speed_at_next_tick = self._speed + self._calc_acceleration_value(time_delta)
        plan_iter = iter(self._plan)
        next(plan_iter)  # skip first
        for plan_point in plan_iter:
            max_turn_speed = plan_point.max_turn_speed
            distance_till_turn = self._distance_till_turn + plan_point.distance_from_current_point

            time_to_stop = (speed_at_next_tick - max_turn_speed) / self._max_break
            distance_to_stop = speed_at_next_tick * time_to_stop - self._max_break * time_to_stop ** 2 / 2
            if distance_to_stop > distance_till_turn:
                return True
        return False

    def _accelerate(self, time_delta):
        self._acceleration = self._calc_acceleration_value(time_delta)
        self._speed += self._acceleration * time_delta

    def _calc_acceleration_value(self, time_delta):
        """
        accelerate or break to move with speed equals max_speed
        -MAX_BREAK <= accelerate <= max_acceleration
        """
        calculated_acceleration = (self._max_speed - self._speed) / time_delta
        return max(-self.MAX_BREAK, min(self._max_acceleration, calculated_acceleration))

    def _break(self, time_delta, emergency=False):
        if emergency:
            calculated_acceleration = (0 - self._speed) / time_delta
            self._acceleration = max(-self.MAX_BREAK, calculated_acceleration)
        else:
            self._acceleration = -self._break_value()
        self._speed += self._acceleration * time_delta
        self._speed = max(0, self._speed)

    def _break_value(self):
        """
        calc break_value to get speed equals max_turn_speed for each plan_point
        and return maximum value.
        In common cases it should return value in range: 0 <= value <= max_break
        because method _want_to_break calculating using value max_break
        but in emergency cases or when madness suddenly decreased just before the crossroad
        return value will be in range 0 <= value <= MAX_BREAK
        """
        max_a = 0
        plan_iter = iter(self._plan)
        next(plan_iter)  # skip first
        for plan_point in plan_iter:
            max_turn_speed = plan_point.max_turn_speed
            distance_till_turn = self._distance_till_turn + plan_point.distance_from_current_point

            v_delta = max(self._speed - max_turn_speed, 0)
            if distance_till_turn != 0:
                a = (self._speed * v_delta - v_delta ** 2 / 2) / distance_till_turn
            else:
                a = 0

            # a - always positive, because self.speed > v_delta / 2
            a = min(a, self.MAX_BREAK)
            max_a = max(max_a, a)

        return max_a

    def _is_time_to_turn(self, time_delta):
        return self._speed * time_delta > self._distance_till_turn

    def _turn_and_move(self, time_delta):
        assert self._speed > 0
        move_distance = self._speed * time_delta
        while move_distance > self._distance_till_turn:
            self._move(self._distance_till_turn, 1)
            move_distance -= self._distance_till_turn
            self._x = self._current.x
            self._y = self._current.y
            self._turn_angle = self._current_turn_angle
            self._angle = math.atan2(self._next.y - self._current.y, self._next.x - self._current.x)
            self._update_plan()
            self._distance_till_turn = distance(Position(self._x, self._y), self._current)
        self._move(move_distance, 1)

    def _change_line(self, time_delta):
        if self._speed >= self.MIN_SPEED:
            direction = self._get_change_line_direction()
        else:
            direction = 0

        if direction != 0:
            forw_speed = self._speed * time_delta
            self._turn_angle = math.atan2(direction * self.LINE_WIDTH, forw_speed)
            self._line_offset += direction
            self._enable_turn_signal(TurnSignal.LEFT if direction < 0 else TurnSignal.RIGHT)
        else:
            self._turn_angle = 0

    def _get_change_line_direction(self):
        if self._command_to_stop:
            if self._line_offset < 1:
                return 1
        else:
            if random.random() < self.LINE_CHANGE_CHANCE:
                return random.choice([-1, 1]) if self._line_offset == 0 else -self._line_offset
        return 0

    def _show_turn_signal_if_needed(self):
        if abs(self._current_turn_angle) > self.TURN_SIGNAL_ANGLE_THRESHOLD \
                and self._distance_till_turn < self.TURN_SIGNAL_DISTANCE:
            self._enable_turn_signal(TurnSignal.LEFT if self._current_turn_angle < 0 else TurnSignal.RIGHT)

    def _enable_turn_signal(self, turn_signal):
        self._turn_signal_countdown = self.TURN_SIGNAL_TICKS
        self._turn_signal = turn_signal

    def _move(self, speed, time_delta):
        path = speed * time_delta
        self._update_odometer(path)
        self._x += math.cos(self._angle) * path
        self._y += math.sin(self._angle) * path

    def _update_odometer(self, path):
        self._odometer += path
        self._gas_range -= path
        if self._gas_range <= 50000:  # refill gas
            self._gas_range += 431000

    def _calc_turn_angle_to_next_point(self):
        next_angle = math.atan2(self._next.y - self._current.y, self._next.x - self._current.x)
        turn_angle = self._angle - next_angle
        if turn_angle > math.pi:
            turn_angle -= 2 * math.pi
        if turn_angle < -math.pi:
            turn_angle += 2 * math.pi
        return turn_angle

    def _update_plan(self):
        self._plan.popleft()
        delta_distance = distance(self._plan[0].vertex, self._plan[1].vertex)
        plan_iter = iter(self._plan)
        next(plan_iter)  # skip first
        for plan_point in plan_iter:
            plan_point.distance_from_current_point -= delta_distance
        self._add_point_to_plan()

    def _update_madness_if_needed(self):
        if self.change_madness_periodically:
            self._ticks_till_next_madness -= 1
            if self._ticks_till_next_madness == 0:
                self.madness = random.random() * 0.5 + 0.5

    def get_data(self):
        return {
            'ac_stat': 0,  # Air conditioning status
            'acc_mode': False,  # Cruise Switch: ACC or ESC mode pressed
            'airtemp_outsd': int(round(self.airtemp_outsd)),  # Outside air temperature
            'aud_mode_adv': False,  # Audio-mode advance
            'aus': False,  # Cruise Switch: Cancel Pressed
            'auto_stat': 0,  # Automatic temperature control status
            'autodfgstat': 7,  # Automatic defog status
            'avgfuellvl': self.fuel_level,  # Average filtered fuel level in liters
            'batt_volt': int(round(self.batt_volt)),  # System voltage
            'brk_stat': self.stop_signal,  # Brake state
            'cell_vr': 0,  # Cell Phone/Voice Recognition Request
            'cruise_tgl': False,  # Cruise Switch: On/Off  Pressed
            'defrost_sel': False,  # Defrost select switch
            'dn_arw_step_rq': 0,  # Down Arrow Request / Odometer Trip Reset
            'dr_lk_stat': 2,  # Door lock status
            'drv_ajar': self.drv_ajar,  # Driver door ajar (1 = Door Ajar)
            'drv_seatbelt': self.drv_seatbelt,  # Drivers seat belt status
            'ebl_stat': 2,  # Electric backlite status
            'engcooltemp': 26,  # Engine coolant temperature
            'engoiltemp': int(round(self.engoiltemp)),  # Oil temperature
            'engrpm': self.rpm,  # Engine revolutions per minute
            'engstyle': 7,  # Engine output version
            'fg_ajar': False,  # Flipper glass ajar
            'fl_hs_stat': 0,  # Front left heated seat status
            'fl_vs_stat': 0,  # Front left vented seat status
            'fr_hs_stat': 0,  # Front right heated seat status
            'fr_vs_stat': 0,  # Front right vented seat status
            'ft_drv_atc_temp': 72,  # Front driver HVAC control auto temperature status
            'ft_drv_mtc_temp': 127,  # Front driver HVAC control manual temperature status
            'ft_hvac_blw_fn_sp': 0,  # Front HVAC blower fan speed status in 'bars'
            'ft_hvac_ctrl_stat': 0,  # Front HVAC control status
            'ft_hvac_md_stat': 15,  # Front HVAC control mode status
            'ft_psg_atc_temp': 72,  # Front passenger HVAC control auto temperature status
            'ft_psg_mtc_temp': 127,  # Front passenger HVAC control manual temperature status
            'gas_range': self.gas_range,  # Gas range or DTE
            'gr': self.gear,  # Current Gear
            'hazard_status': self.turn_signal == TurnSignal.EMERGENCY,  # Hazard lamps
            'hibmlvr_stat': 0,  # High beam lever state
            'hl_stat': 0,  # Headlamp status
            'hrnsw_psd': False,  # Horn switch pressed (1=pressed)
            'hrnswpsd': False,  # Horn switch pressed (1=pressed)
            'hsw_stat': False,  # Heated steering wheel status
            'l_r_ajar': False,  # Left rear door ajar
            'lrw': int(self.steering_wheel_angle),  # Steering wheel angle
            'max_acsts': 0,  # Maximum A/C status
            'menu_rq': 0,  # Menu Switch Request / Back
            'odo': self.odometer,  # Odometer km
            'oil_press': int(round(self.oil_press)),  # Oil pressure
            'preset_cfg': 0,  # Preset Configuration
            'prkbrkstat': 7,  # Parking brake status
            'prnd_stat': 0,  # PRND Status
            'psg_ajar': False,  # Passenger door ajar
            'psg_ods_stat': 0,  # Passenger Occupant Detection Sensor Status
            'psg_seatbelt': 0,  # Passengers seat belt status
            'r_r_ajar': False,  # Right rear door ajar
            'recirc_stat': 0,  # Recirculation status
            'reserved_1': False,  # Reserved
            'reserved_2': 0,  # Reserved
            'reserved_3': 0,  # Reserved
            'reserved_4': 0,  # Reserved
            'reserved_5': 0,  # Reserved
            'rl_heat_stat': 0,  # Rear left heat status
            'rl_vent_off': False,  # Rear left vent off request
            'rr_dr_unlkd': self.rr_dr_unlkd,  # Rear door (hatch / lift gate is unlocked
            'rr_heat_stat': 0,  # Rear right heat status
            'rr_vent_off': False,  # Rear right vent off request
            'rt_arw_rst_rq': 0,  # Right Arrow Reset Request
            's_minus_b': False,  # Cruise Switch: Coast or Set/Decel Pressed
            's_plus_b': False,  # Cruise Switch: Resume/Accel Pressed
            'seek': 0,  # Seek up/down
            'stw_lvr_stat': 0,  # Steering wheel lever state
            'stw_temp': 20,  # Steering wheel temperature
            'sync_stat': False,  # Synchronization Status
            'tirepressfl': 27,  # Tire pressure front left
            'tirepressfr': 27,  # Tire pressure front right
            'tirepressrl': int(round(self.tire_pressure)),  # Tire pressure rear left
            'tirepressrr': 27,  # Tire pressure rear right
            'tirepressspr': 27,  # Tire pressure spare tire
            'turnind_lt_on': self.turn_signal == TurnSignal.LEFT,  # Turn indication left is on
            'turnind_rt_on': self.turn_signal == TurnSignal.RIGHT,  # Turn indication right is on
            # Turn indicator lever state
            'turnindlvr_stat': self.turn_signal if self.turn_signal != TurnSignal.EMERGENCY else 0,
            'up_arw_rq': 0,  # Up Arrow Request / Step
            'vc_body_style': 7,  # Body style
            'vc_country': 2,  # Country Code
            'vc_model_year': 225,  # Model year
            'vc_veh_line': 29,  # Vehicle line
            'veh_int_temp': int(round(self.veh_int_temp)),  # Vehicle interior temperature
            'veh_speed': self.speed_kmph,  # Vehicle speed
            'vehspddisp': self.speed_kmph,  # Vehicle speed - displayed
            'vol': 0,  # Volume up/down
            'wa': False,  # Cruise Switch: distance / launch mode pressed
            'wh_up': False,  # Cruise Switch: Implausible State=1
            'wprsw6posn': 0,  # Wiper switch (6 stages) position
            'wprwash_r_sw_posn_v3': 0,  # Backlite wiper/washer switch position
            'wprwashsw_psd': 0,  # Front wiper switch pressed

            'lat': self.lat,
            'lon': self.lon,
            'wiper': int(round(self.wiper)),
            'intensity': int(round(self.intensity)),
            "move_to_rectangle": self.move_to_rectangle,
            "in_rectangle": self.in_rectangle,
            **self.rectangle,
        }

    @property
    def x(self):
        if self._line_offset == 0:
            return self._x

        angle = self._angle + (math.pi / 2 if self._line_offset < 0 else -math.pi / 2)
        dx = math.cos(angle) * abs(self._line_offset) * self.LINE_WIDTH
        return self._x + dx

    @property
    def y(self):
        if self._line_offset == 0:
            return self._y

        angle = self._angle + (math.pi / 2 if self._line_offset < 0 else -math.pi / 2)
        dy = math.sin(angle) * abs(self._line_offset) * self.LINE_WIDTH
        return self._y + dy

    @property
    def _current_turn_angle(self):
        return self._plan[1].turn_angle

    @property
    def _prev(self):
        return self._plan[0].vertex

    @property
    def _current(self):
        return self._plan[1].vertex

    @property
    def _next(self):
        return self._plan[2].vertex

    @property
    def madness(self):
        return self._madness

    @madness.setter
    def madness(self, madness):
        assert 0 < madness <= 1
        self._madness = madness
        self._max_speed = self.MIN_SPEED + (self.MAX_SPEED - self.MIN_SPEED) * madness
        self._max_acceleration = self.MIN_ACCELERATION + (self.MAX_ACCELERATION - self.MIN_ACCELERATION) * madness
        self._max_break = self.MIN_BREAK + (self.MAX_BREAK - self.MIN_BREAK) * madness
        for cur in iter(self._plan):
            cur.max_turn_speed = self._calc_max_turn_speed(cur.turn_angle)
        self._ticks_till_next_madness = self.MADNESS_CHANGE_TICKS

    @property
    def lat(self):
        return self._vertex_pool.y_to_lat(self.y)

    @property
    def lon(self):
        return self._vertex_pool.x_to_lon(self.x)

    @property
    def fuel_consumption(self):
        return self.rpm * self.MIN_FUEL_CONSUMPTION / self.MIN_RPM

    @property
    def in_rectangle(self):
        result = None
        if self._rectangle:
            result = self._in_rectangle()
        return result

    @property
    def move_to_rectangle(self):
        return self._rectangle_to

    @property
    def rectangle(self):
        result = {
            "rectangle_long0": None,
            "rectangle_lat0": None,
            "rectangle_long1": None,
            "rectangle_lat1": None
        }

        rectangle = self._rectangle
        if rectangle:
            result = {
                "rectangle_long0": rectangle[0].longitude,
                "rectangle_lat0": rectangle[0].latitude,
                "rectangle_long1": rectangle[1].longitude,
                "rectangle_lat1": rectangle[1].latitude
            }
        return result

    @property
    def acceleration(self):
        return self._acceleration

    @property
    def turn_angle(self):
        return self._turn_angle

    @RandomShift(-10, 10)
    def steering_wheel_angle(self):
        return int(self.turn_angle / math.pi * 530)  # change it to be beauty. result must be between -539 and 540

    @RandomShift(-5, 5)
    def oil_press(self):
        return 249

    @RandomShift(-4, 4)
    def engoiltemp(self):
        return 95

    @RandomShift(-0.5, 0.5)
    def batt_volt(self):
        return 11.52

    @property
    def angle(self):
        return self._angle

    @property
    def speed(self):
        return self._speed

    @property
    def speed_kmph(self):
        return int(self.speed * self.MPS_TO_KMPH)

    @property
    def max_speed(self):
        return self._max_speed

    @property
    def max_break(self):
        return self._max_break

    @property
    def max_acceleration(self):
        return self._max_acceleration

    @property
    def vertex_pool(self):
        return self._vertex_pool

    @property
    def tick(self):
        return self._tick

    @property
    def stop_signal(self):
        return int(self.acceleration <= -self.STOP_SIGNAL_BREAK_THRESHOLD)

    @property
    def turn_signal(self):
        return self._turn_signal

    @property
    def gear(self):
        if self.speed < self.MIN_SPEED and self._command_to_stop:
            return 0
        else:
            return min(int(self.speed // self.SPEED_TO_TURN_GEAR), 4) + 1

    @property
    def rpm(self):
        if self.gear == 0:
            return self.MIN_RPM
        elif self.gear == 1:
            return int((self.speed % self.SPEED_TO_TURN_GEAR) / self.SPEED_TO_TURN_GEAR * 1500 + 1500)
        else:
            return int((self.speed % self.SPEED_TO_TURN_GEAR) / self.SPEED_TO_TURN_GEAR * 1000 + 2500)

    @property
    def odometer(self):
        return int(self._odometer // 1000)

    @property
    def gas_range(self):
        return int(self._gas_range // 1000)

    @property
    def fuel_level(self):
        return int(self.FUEL_CONSUMPTION / 100 * self.gas_range)

    @RandomShift(-1, 1)
    def airtemp_outsd(self):
        return 20

    @RandomShift(-1, 1)
    def veh_int_temp(self):
        return 22

    @RandomShift(-2, 2, None, True)
    def wiper(self):
        return 2

    @RandomShift(-4, 4, None, True)
    def intensity(self):
        return 4

    def tire_break(self):
        """Tries to brake tire. Returns True on success, False otherwise. You can't brake tire if it is already broken
        """
        if self._replace_tire_countdown == self.REPLACE_TIRE_COUNTDOWN:
            self._broken_tire = True
            return True
        else:
            return False

    def command_stop(self):
        """Command to emergency stop the car. Returns True on success, False otherwise.
        """
        self._command_to_stop = True
        return True

    def command_go(self):
        """Command to continue riding after command_stop(). Returns True on success, False otherwise.
        You can't exec command_go() if tire is broken.
        """
        if not self._broken_tire:
            self._command_to_stop = False
            return True
        else:
            return False


def main():
    import time
    vp = VertexPool('map.json')
    emulator = Emulator(vp)
    start = time.time()
    while True:
        try:
            emulator.update(0.1)
            if emulator.tick % 100000 == 0:
                end = time.time()
                print("performance {:.2f} ticks per second".format(100000 / (end - start)))
                start = end
        except KeyboardInterrupt:
            print("Keyboard interrupt")
            return
        except Exception as ex:
            import traceback
            print("Unexpected exception: {}".format(ex))
            print(''.join(traceback.format_exception(None, ex, ex.__traceback__)), file=sys.stderr, flush=True)
            import pickle
            pickle.dump(emulator, open('emulator_{}.dmp'.format(random.randint(0, 10000)), 'wb'))
            return


if __name__ == '__main__':
    main()
