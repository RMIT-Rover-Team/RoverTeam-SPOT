testSlave:
	@g++ -o DummyPayloadSim DummyPayload.cpp ../libuniversalcan/RoverCanSlave.cpp ../libuniversalcan/SocketCanWrapper.cpp ../libuniversalcan/CommandUtils.cpp -I. -I../libuniversalcan/ 

UniCanMon:
	@g++ -o UniCanMon UniCanMon.cpp ../libuniversalcan/RoverCanMaster.cpp ../libuniversalcan/SocketCanWrapper.cpp ../libuniversalcan/CommandUtils.cpp -I. -I../libuniversalcan/ 


all: testMaster testSlave UniCanMon

clean:
	@rm -f DummyPayloadSim UniCanMon