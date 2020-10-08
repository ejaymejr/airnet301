try:
    # Made for the Airnet 301 interfacing through an ADS1115 through I2C to a RPI
    import socket
    import os
    from dotenv import load_dotenv
    # Load secrets from .env file
    load_dotenv(verbose=True)

    # pip3 install adafruit-circuitpython-ads1x15
    # pip3 install mysql-connector-python

    # Config
    deviceID = socket.gethostname()
    thresholdPointThree = int(os.getenv("pointThreeThres"))
    thresholdPointFive = int(os.getenv("pointFiveThres"))
    consecAlertThreshold = int(os.getenv("consecAlert"))
    resistorType = int(os.getenv("resistorType"))

    # DotEnv
    # S3
    import boto3
    # ADS1115
    import time
    import board
    import busio
    import adafruit_ads1x15.ads1015 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
    # Math
    import math
    # Picamera
    from picamera import PiCamera
    # MySql
    import mysql.connector
    import string
    # Datetime
    from datetime import datetime
    # Sys for arguments
    import sys

    os.system("rm images/*")

    # Setting up PiCamera
    camera = PiCamera()
    camera.resolution = (1024, 768)

    # Load arguments given
    sysArgs = sys.argv

    # Create the I2C bus
    i2c = busio.I2C(board.SCL, board.SDA)

    # Create the ADC object using the I2C bus
    ads = ADS.ADS1015(i2c, 2/3)

    # Create single-ended input on channels
    chan0 = AnalogIn(ads, ADS.P1)
    chan1 = AnalogIn(ads, ADS.P2)
    chan2 = AnalogIn(ads, ADS.P3)

    # S3
    session = boto3.session.Session()
    client = session.client('s3', region_name='sgp1', endpoint_url='https://sgp1.digitaloceanspaces.com', aws_access_key_id=os.getenv("aws_key"), aws_secret_access_key=os.getenv("aws_secret_key"))

    # client.upload_file('/path/to/file.ext',  # Path to local file
    #                    'airnet301',  # Name of Space
    #                    'file.ext')  # Name for remote file

    # Remaps a value in a given range to a new value in another range
    def remap(oldMin, oldMax, newMin, newMax, oldValue):
        oldRange = (oldMax - oldMin)  
        newRange = (newMax - newMin)  
        newValue = (((oldValue - oldMin) * newRange) / oldRange) + newMin
        return newValue


    try:
        connection = None
        if(os.getenv("db_password")):
            connection = mysql.connector.connect(
            user=os.getenv("db_user"),
            host=os.getenv("db_ip"),
            database=os.getenv("db_database"),
            charset='utf8',
            port='3306')
        else:
            connection = mysql.connector.connect(
            user=os.getenv("db_user"),
            password=os.getenv("db_password"),
            host=os.getenv("db_ip"),
            database=os.getenv("db_database"),
            charset='utf8',
            port='3306')

        
        while True:
            time.sleep(1/2)
            if(math.floor(chan2.voltage) > ((4 * resistorType)/1000)):
                print("Starting recording!")
                break
            else:
                print("Waiting for status to be higher than "+str(((4 * resistorType)/1000))+" volt,\ncurrent: "+str(math.floor(chan2.voltage)))
                
        # The title for logging
        print("{:>16}\t{:>16}\t{:>16}\t{:>16}".format('No.', '0.3um', '0.5um', 'Status'))
        # Counting mechanic
        no = 0
        consecAlert = 0
        while True:
            doUpload = False
            # Get UNIX timestamp at the moment, used as file ID
            timeStamp = time.time()
            
            minRange = (4 * resistorType)/1000
            maxRange = (20 * resistorType)/1000
            # Get count for 0.3 micron
            #0.96,4.8
            count0 = round(remap(minRange,maxRange,0,1000,chan0.voltage)) * 10
            # Get count for 0.5 micron
            count1 = round(remap(minRange,maxRange,0,1000,chan1.voltage)) * 10
        
            if(count0 < 0):
                count0 = 0
            if(count1 < 0):
                count1 = 0
            # Get the corresponding status text
            statusVoltage = round(chan2.voltage)
            textStatus = ""
        
            if (statusVoltage == math.floor((8 * resistorType)/1000)):
                textStatus = "Flow: OK, Laser: OK"
            elif (statusVoltage == math.floor((12 * resistorType)/1000)):
                textStatus = "Flow: OK, Laser: BAD"
            elif (statusVoltage == math.floor((16 * resistorType)/1000)):
                textStatus = "Flow: BAD, Laser: OK"
            elif (statusVoltage == math.floor((20 * resistorType)/1000)):
                textStatus = "Flow: BAD, Laser: BAD"
            else:
                textStatus = "Unknown status, this will be logged. voltage: "+str(chan0.voltage)
        
            # Log results in console
            print("{:>16}\t{:>16}\t{:>16}\t{:>16}".format(no, count0, count1, textStatus))
            
            isBad = False
            filename = str(deviceID)+"-"+str(timeStamp)+".jpg"
            if(count0 >= thresholdPointThree or count1 >= thresholdPointFive or statusVoltage != math.floor((8 * resistorType)/1000)):
                consecAlert += 1
                print("\t\033[91m"+"Consec: "+str(consecAlert)+"\033[0m")
                if(consecAlert >= consecAlertThreshold):
                    camera.capture("images/"+filename)
                    print("\t\033[91m"+"Alert!"+"\033[0m")
                    isBad = True
                    consecAlert = 0
                    doUpload = True
                else:
                    filename = "There is no image within these walls"
                
            else:
                consecAlert = 0
                filename = "There is no image within these walls"
                
            # Push results to DB
            sql="INSERT INTO `airnet301_test` (`id`, `deviceID`, `date`, `0.3`, `0.5`, `status`, `image`, `isBad`) VALUES (NULL, '{}', CURRENT_TIMESTAMP, {}, {}, {}, '{}', {});".format(deviceID, count0, count1, statusVoltage, filename, isBad)
            #print(sql)
            mycursor = connection.cursor()
            mycursor.execute(sql)
            
            if(doUpload):
                client.upload_file("images/"+filename, 'airnet301', filename, {'ACL': 'public-read'})
                            
            # Add one to count
            no=no+1
            # Wait for a minute
            time.sleep(60)
        
    except mysql.connector.Error as e:
        print(e)
except Exception as e:
    print(str(e))
    f = open("log.txt", "a")
    f.write(str(e))
    f.close()
