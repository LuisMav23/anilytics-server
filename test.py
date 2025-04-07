import datetime
import pytz

def main():
    # Get current UTC time
    utc_now = datetime.datetime.now(pytz.utc)
    print("Current UTC time:", utc_now.strftime("%Y-%m-%d %H:%M:%S %Z%z"))

    # List of timezones to test
    timezones = ['America/New_York', 'Europe/London', 'Asia/Tokyo', 'Australia/Sydney', 'Asia/Manila']

    for tz_name in timezones:
        tz = pytz.timezone(tz_name)
        local_time = utc_now.astimezone(tz)
        print(f"Local time in {tz_name}: {local_time.strftime('%Y-%m-%d %H:%M:%S %Z%z')}")

if __name__ == "__main__":
    main()