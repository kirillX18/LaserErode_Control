from LaserErosionHardwareStubs import LaserErosionRobotController


if __name__ == '__main__':
    controller = LaserErosionRobotController()
    print(controller.get_system_status())

    controller.ac_dc_converter.turn_on()
    controller.lid_sensor.set_lid_state(True)

    controller.initialize()
    controller.move_motor_to(300)
    controller.start_process()
    print(controller.get_system_status())
    controller.set_temperature_mock(75)
    print(controller.get_system_status())