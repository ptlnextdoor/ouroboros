clear;

a=fscanfMat("one.csv");

v=a(:,1:16);
i=a(:,17:17+15);
t=a(:,17+16:17+16+15);

[r,c]=size(a);
time=0:r-1;
time=time/1000; //Sample rate 1KHz
time=time';

figure(1);
clf

subplot(412);
plot(time,sum(v.*i,'c')); ylabel("Total power [W]");
subplot(212);
plot(time,t); ylabel("Temperature °C");
