import RPi.GPIO as GPIO
import time
from datetime import datetime, timedelta
from tapo_plug.tapo import set_state as set_tapo_state
import requests

API_KEY = ''
LAT = 0
LON = 0

TURN_OFF_AFTER_SECONDS = 60*1
PERIODIC_TURN_OFF_INTERVAL_SECONDS = TURN_OFF_AFTER_SECONDS # if the powerplug is already off, send off signal again every X seconds
SENSOR_PINS = [23, 24]
SENSOR_PINS = [24]

# gpio setup
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
for pin in SENSOR_PINS:
    GPIO.setup(pin, GPIO.IN)

# globals
latest_intruder_incoming = None
latest_intruder_left = None
power_plug_turned_on = False

SUNRISE_SUNSET_INFO = {
    'sunrise': None,
    'sunset': None,
    'date': None
}

ENABLE_LOGGING = True

def log(*args):
    if ENABLE_LOGGING:
        print(*args)

def get_time(unix_timestamp, pad):
    # utcoffset_seconds = -(time.timezone if (time.localtime().tm_isdst == 0) else time.altzone)
    dt = datetime.fromtimestamp(unix_timestamp) #+ timedelta(seconds=utcoffset_seconds)
    return dt + timedelta(minutes=pad)


def get_todays_sunrise_sunset_info():
    global SUNRISE_SUNSET_INFO
    global API_KEY
    global LAT
    global LON

    date = str(datetime.now().date())

    if SUNRISE_SUNSET_INFO['date'] != date:
        log('requesting new sunrise/sunset info from API...')
        URL = f'https://api.openweathermap.org/data/2.5/weather?appid={API_KEY}&mode=json&units=metric&lang=en&lat={LAT}&lon={LON}'

        try:
            response = requests.get(URL, timeout=5)

            weather = response.json()

            # calculate dynamic padding based on day/night duration
            day_duration = (weather['sys']['sunset'] - weather['sys']['sunrise']) * 1.0 / 3600
            night_duration = 24 - day_duration

            sunrise_factor = 7
            sunset_factor = -2.5

            PAD_SUNRISE = int(night_duration * sunrise_factor) # as of 2025-10-30, a bit more than 90 seems good?
            PAD_SUNSET = int(night_duration * sunset_factor) # as of 2025-10-30, about -30 seems good?

            SUNRISE_SUNSET_INFO = {
                'sunrise': get_time(weather['sys']['sunrise'], PAD_SUNRISE),
                'sunset': get_time(weather['sys']['sunset'], PAD_SUNSET),
                'date': date
            }
        except requests.RequestException as e:
            log('Error fetching sunrise/sunset info:', e)
            # In case of an error, keep the previous values if they exist
            if SUNRISE_SUNSET_INFO['sunrise'] is None or SUNRISE_SUNSET_INFO['sunset'] is None:
                raise e
        except Exception as e:
            raise e

        log('new sunrise/sunset info:')
        log('\t', 'sunrise:', SUNRISE_SUNSET_INFO['sunrise'].strftime('%H:%M:%S'), '(pad', PAD_SUNRISE, 'min)')
        log('\t', 'sunset: ', SUNRISE_SUNSET_INFO['sunset'].strftime('%H:%M:%S'), '(pad', PAD_SUNSET, 'min)')
        log('\t', 'date:   ', SUNRISE_SUNSET_INFO['date'])

    return SUNRISE_SUNSET_INFO['sunrise'], SUNRISE_SUNSET_INFO['sunset']


def is_within_working_hours():
    sunrise, sunset = get_todays_sunrise_sunset_info()
    now = datetime.now()

    # log('Sunrise at', sunrise.strftime('%H:%M:%S'), 'Sunset at', sunset.strftime('%H:%M:%S'), 'Current time is', now.strftime('%H:%M:%S'))

    # if now <= sunrise or now >= sunset:
    #     log('Within working hours, turning on the plug.')
    # else:
    #     log('Outside working hours, not turning on the plug.')

    return now <= sunrise or now >= sunset


def get_formatted_time_difference(dt):
    delta = datetime.now() - dt
    # minutes, seconds = divmod(delta.total_seconds(), 60)
    # return f'{int(minutes):02}:{int(seconds):02}'
    # hours, minutes, seconds = divmod(delta.total_seconds(), 3600)
    # return f'{int(hours):02}:{int(minutes):02}:{int(seconds):02}'

    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    seconds = delta.seconds % 60
    return f'{hours:02}:{minutes:02}:{seconds:02}'

def get_formatted_timestamp():
    # return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return datetime.now().strftime('%H:%M:%S')

def set_power_plug_state(state):
    global power_plug_turned_on

    if state == 'on' and not power_plug_turned_on:
        set_tapo_state(state)
        power_plug_turned_on = True
    elif state == 'off':
        if power_plug_turned_on:
            set_tapo_state(state)
            power_plug_turned_on = False

def on_event(gpio_pin):
    global latest_intruder_incoming
    global latest_intruder_left


    if gpio_pin is None:
        current_state = None
    else:
        current_state = GPIO.input(gpio_pin)

    if current_state == 1:
        latest_intruder_incoming = datetime.now()

        if latest_intruder_left:
            # log(gpio_pin, 'state changed to HIGH at', get_formatted_timestamp(), 'after', get_formatted_time_difference(latest_intruder_left))
            # log('Intruder returned after', get_formatted_time_difference(latest_intruder_left), 'at', get_formatted_timestamp())
            latest_intruder_left = None
        else:
            # log(gpio_pin, 'state changed to HIGH at', get_formatted_timestamp())
            log('Intruder at', get_formatted_timestamp())

        if is_within_working_hours():
            set_power_plug_state('on')

    else:
        latest_intruder_left = datetime.now()

        if latest_intruder_incoming:
            # log('Intruder left     after', get_formatted_time_difference(latest_intruder_incoming))
            latest_intruder_incoming = None
        # else:
            # log('Intruder left at', get_formatted_timestamp())

        # log(gpio_pin,'state changed to LOW  at', get_formatted_timestamp())


def main_event_loop():
    GPIO.add_event_detect(SENSOR_PIN, GPIO.BOTH, callback=on_event)
    
    while True:
        time.sleep(5)

def get_any_sensor_high():
    for pin in SENSOR_PINS:
        if GPIO.input(pin) == 1:
            return {
                'state': True,
                'pin': pin
            }
    return {
        'state': False,
        'pin': None
    }

def main_true_loop():
    global latest_intruder_left

    previous_state = {
        'state': False,
        'pin': None
    }
    set_power_plug_state('off')

    last_turn_off_signal_sent = None

    while True:
        current_state = get_any_sensor_high()
        # log(current_state, get_formatted_timestamp())

        if current_state['state'] != previous_state['state']:
            if not current_state['state']:
                event_pin = previous_state['pin']
            else:
                event_pin = current_state['pin']
            on_event(event_pin)
            previous_state = current_state

        if not current_state['state'] and latest_intruder_left and (datetime.now() - latest_intruder_left).total_seconds() > TURN_OFF_AFTER_SECONDS:
            global power_plug_turned_on
            if power_plug_turned_on:
                log('No intruder for', get_formatted_time_difference(latest_intruder_left), 'turning off at', get_formatted_timestamp())
                last_turn_off_signal_sent = datetime.now()
                set_power_plug_state('off')
            elif last_turn_off_signal_sent is not None and (datetime.now() - last_turn_off_signal_sent).total_seconds() > PERIODIC_TURN_OFF_INTERVAL_SECONDS:
                log('No intruder for', get_formatted_time_difference(latest_intruder_left), 'plug already off, but sending off signal again at', get_formatted_timestamp())
                last_turn_off_signal_sent = datetime.now()
                set_power_plug_state('off')

        time.sleep(0.1)


def main():
    get_todays_sunrise_sunset_info()

    current_state = get_any_sensor_high()
    log('Startup:', get_formatted_timestamp(), 'someone is here on pin ' + str(current_state['pin']) + '!' if current_state['state'] else 'no one here!')

    try:
        # main_event_loop()
        main_true_loop()
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
        set_power_plug_state('off')

if __name__ == '__main__':
    main()
