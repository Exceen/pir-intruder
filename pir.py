import RPi.GPIO as GPIO
import time
from datetime import datetime
from tapo_plug.tapo import set_state

TURN_OFF_AFTER_SECONDS = 60*15 # 15 minutes
SENSOR_PINS = [23, 24]

# gpio setup
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
for pin in SENSOR_PINS:
    GPIO.setup(pin, GPIO.IN)

# globals
latest_intruder_incoming = None
latest_intruder_left = None
power_plug_turned_on = False


def set_power_plug_state(state):
    global power_plug_turned_on

    if state == 'on' and not power_plug_turned_on:
        set_state(state)
        power_plug_turned_on = True
    elif state == 'off':
        if power_plug_turned_on:
            set_state(state)
            power_plug_turned_on = False

def on_event(gpio_pin):
    global latest_intruder_incoming
    global latest_intruder_left


    if gpio_pin is None:
        current_state = None
    else:
        current_state = GPIO.input(gpio_pin)

    if current_state:
        latest_intruder_incoming = datetime.now()

        if latest_intruder_left:
            print(gpio_pin, 'state changed to HIGH at', get_formatted_timestamp(), 'after', get_formatted_time_difference(latest_intruder_left))
            # print('Intruder returned after', get_formatted_time_difference(latest_intruder_left), 'at', get_formatted_timestamp())
            latest_intruder_left = None
        else:
            print(gpio_pin, 'state changed to HIGH at', get_formatted_timestamp())
            # print('Intruder at', get_formatted_timestamp())

        set_power_plug_state('on')

    else:
        latest_intruder_left = datetime.now()

        if latest_intruder_incoming:
            # print('Intruder left     after', get_formatted_time_difference(latest_intruder_incoming))
            latest_intruder_incoming = None
        # else:
            # print('Intruder left at', get_formatted_timestamp())

        print(gpio_pin,'state changed to LOW  at', get_formatted_timestamp())


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


def main_event_loop():
    GPIO.add_event_detect(SENSOR_PIN, GPIO.BOTH, callback=on_event)
    
    while True:
        time.sleep(5)
        

def main_true_loop():
    global latest_intruder_left

    previous_state = get_any_sensor_high()
    set_power_plug_state('on' if previous_state['state'] else 'off') # set initial state

    while True:
        current_state = get_any_sensor_high()
        # print(current_state, get_formatted_timestamp())

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
                print('No intruder for', get_formatted_time_difference(latest_intruder_left), 'turning off at', get_formatted_timestamp())
            set_power_plug_state('off')
        time.sleep(0.1)


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


def main():
    current_state = get_any_sensor_high()
    print('Startup:', get_formatted_timestamp(), 'someone is here on pin ' + str(current_state['pin']) + '!' if current_state['state'] else 'no one here!')

    try:
        # main_event_loop()
        main_true_loop()
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
        set_state('off')


if __name__ == '__main__':
    main()