#include <string>
#include <vector>
#include <poll.h>
#include <assert.h>

#include "socket.hh"

using namespace std;

/* send packet from lte to ethernet to punch a NAT hole */
/* Use this packet at the ethernet to infer end point */
Socket::Address getNatAddr( const Socket & sender, const Socket::Address & dest,
			      const Socket & receiver )
{
  char buf[ 10 ];
  for ( int i = 0; i < 10; i++ ) {
    buf[ i ] = rand() % 256;
  }
  
  string to_send( buf, 10 );

  sender.send( Socket::Packet( dest, to_send ) );
  Socket::Packet received( receiver.recv() );

  if ( received.payload != to_send ) {
    fprintf( stderr, "Bad packet received while getting NAT addresses.\n" );
    exit( 1 );
  }

  return received.addr;
}
/* global values */
uint64_t stt=0;
/* maintain a vector of packet statistics , only sent_time is used for stt */
struct packetstat {
 uint64_t sent_time;
 int dest;
 bool received;
};
/* stt is written by the rx, packetstat is written by the sender */
const int NUM_PACKETS=10000;
vector<struct packetstat> packetstats( NUM_PACKETS );
const double ALPHA=0.125;
const int TARGET_TT=250000; /* 250 ms or 250000 us */
const int epsilon=5000 ;    /* 5 ms leeway around that. */

/* update smoothed transit time based on new value */ 
uint64_t updateStt(uint64_t tt, uint64_t stt) {
   return uint64_t(ALPHA*((double)tt) + (1-ALPHA)*((double)stt)) ;
}
/* check for congestion based on rtt and change sleepTime accordingly */
uint32_t checkCongestion(uint64_t stt,double currentRate) {
   if(stt>TARGET_TT+epsilon) return (currentRate/2); /* Multiplicative decrease */ 
   else if(stt<TARGET_TT -epsilon) return (currentRate-1); /*Additive increase in some sense */ 
   else return currentRate; /* sit tight */
}
/* lteReceiver */
void* lteReceiver(void* receiverSocket ) {
  Socket lteSocket=*((Socket* )(receiverSocket));
  struct pollfd pollfds[ 1 ];
  for ( int i = 0; i < 1; i++ ) {
    pollfds[ i ].fd = lteSocket.get_sock();
    pollfds[ i ].events = POLLIN;
  }
  while(1) {
       /* now, poll */
    if ( poll( pollfds, 1, -1 ) <= 0 ) {
      perror( "poll" );
      exit( 1 );
    }
    
    for ( int i = 0; i < 1; i++ ) {
      if ( pollfds[ i ].revents & POLLERR ) {
	fprintf( stderr, "Error on LTE %d\n", i );
	exit( 1 );
      }

      if ( pollfds[ i ].revents & POLLIN ) {
	Socket::Packet rec = lteSocket.recv();
	//	assert ( rec.payload.size() == sizeof( packets_sent ) );
        uint64_t receivedTs=rec.timestamp;
        uint64_t seq=*(uint64_t *)rec.payload.data();
        printf("Transit time of packet %lu is %f milliseconds, sent at %lu us , received at %lu us \n",seq,(double)(receivedTs-packetstats[seq].sent_time)/1000,packetstats[seq].sent_time,receivedTs);
        uint64_t tt=receivedTs-packetstats[seq].sent_time;
        stt=updateStt(tt,stt);
       }
    }
  }
}
int main() {
    /* Create and bind Ethernet socket */
    Socket ethernetSocket;
    Socket::Address ethernetAddress( "18.251.7.128", 9000 );
    ethernetSocket.bind( ethernetAddress );
    ethernetSocket.bind_to_device( "eth0" );

    /* Create and bind the LTE socket */
    Socket lteSocket;
    lteSocket.bind( Socket::Address( "10.100.1.1", 9001 ) );
    lteSocket.bind_to_device( "usb0" );

    /* get nat end point */
    Socket::Address lteEndPoint(getNatAddr( lteSocket, ethernetAddress, ethernetSocket ) );
    fprintf( stderr, "LTE = %s\n",lteEndPoint.str().c_str() );

    /* Create lteReceiver thread ,and pass it appropriate params  */
    pthread_t lteReceiverThread;
    if(pthread_create(&lteReceiverThread, NULL, &lteReceiver,&lteSocket ))  {
       printf("Could not create receiver thread \n");
    }
    /* sending loop ie ethernetSender */
    int numSent =0 ; /* number sent out so far */
    double currentPacketRate=100; /*current Rate at the sender, start it out at 100 Hz */
    while(numSent < NUM_PACKETS) {
       /* check current stt , for instantaneous feedback */
       currentPacketRate=checkCongestion(stt,currentPacketRate);
       usleep(1000000/currentPacketRate); /*currentRate is in packets per second, usleep takes us */
       char *seq_encoded = (char *)&numSent;
       packetstats[ numSent ].sent_time = Socket::timestamp(); /* maintain state to calc stt */
       ethernetSocket.send(Socket::Packet(lteEndPoint, string( seq_encoded, 51 ) ) );      
       numSent++;
    }
}
