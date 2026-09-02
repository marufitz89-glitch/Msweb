FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV ANDROID_HOME=/opt/android-sdk
ENV ANDROID_SDK_ROOT=/opt/android-sdk
ENV GRADLE_USER_HOME=/opt/gradle-home

ENV PATH="${PATH}:${ANDROID_HOME}/cmdline-tools/latest/bin:${ANDROID_HOME}/platform-tools"

RUN apt-get update && apt-get install -y \
    openjdk-17-jdk \
    python3 \
    python3-pip \
    wget \
    unzip \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Android SDK
RUN mkdir -p ${ANDROID_HOME}/cmdline-tools

RUN wget -q \
    https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip \
    -O /tmp/android-cmdline.zip

RUN unzip -q /tmp/android-cmdline.zip \
    -d ${ANDROID_HOME}/cmdline-tools

RUN mv \
    ${ANDROID_HOME}/cmdline-tools/cmdline-tools \
    ${ANDROID_HOME}/cmdline-tools/latest

RUN yes | sdkmanager --licenses >/dev/null || true

RUN sdkmanager \
    "platform-tools" \
    "platforms;android-35" \
    "build-tools;35.0.0"

# Gradle 8.7
RUN wget -q \
    https://services.gradle.org/distributions/gradle-8.7-bin.zip \
    -O /tmp/gradle.zip

RUN unzip -q /tmp/gradle.zip -d /opt

ENV PATH="${PATH}:/opt/gradle-8.7/bin"

WORKDIR /app

COPY requirements.txt .

RUN pip3 install \
    --break-system-packages \
    --no-cache-dir \
    -r requirements.txt

COPY build.py .

RUN mkdir -p /tmp/msweb-builds

EXPOSE 10000

CMD ["python3", "build.py"]
